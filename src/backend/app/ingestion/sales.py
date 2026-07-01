import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import case, delete, func, insert, select
from sqlalchemy import text as sql_text
from sqlalchemy import and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.app.ingestion.identifiers import is_sbis_internal_nom_code
from src.backend.app.ingestion.month_ranges import MonthSlice, month_starts_from_slices
from src.backend.app.ingestion.utils import to_decimal
from src.backend.app.integrations.saby.client import SabyClient
from src.backend.app.integrations.saby.schemas import (
    OrderLinePayload,
    RetailOrderPayload,
    iter_order_dicts,
)
from src.backend.app.models import Product, SaleLine, SalesMonthly

logger = logging.getLogger(__name__)

_PAGE_SIZE = 200


async def _build_nom_number_resolver(session: AsyncSession) -> dict[str, str]:
    """Сырой ``NomenclatureNumber`` из чека → ключ ``product.article`` после загрузки складов."""

    rows = (
        await session.execute(
            select(Product.nom_number, Product.article).where(
                Product.nom_number.isnot(None),
                Product.nom_number != "",
            )
        )
    ).all()

    bucket: defaultdict[str, set[str]] = defaultdict(set)
    for nom, art in rows:
        bucket[str(nom).strip()].add(str(art).strip())

    out: dict[str, str] = {}
    for nom, arts in bucket.items():
        arts = {a for a in arts if a}
        if not arts:
            continue
        if len(arts) == 1:
            out[nom] = next(iter(arts))
            continue
        # при дубликатах (старый ключ X… и «правильный» артикул) предпочитаем не‑X
        ordered = sorted(arts, key=lambda a: (is_sbis_internal_nom_code(a), len(a)))
        out[nom] = ordered[0]
    return out


async def refresh_sales_monthly_for_store(
    session: AsyncSession,
    store_id: int,
    overall_from: datetime,
    overall_to_exclusive: datetime,
    month_dates: list[date],
    *,
    now: datetime,
) -> None:
    """Перестроить `sales_monthly` для точки из `sale_line` за интервал месяцев."""

    if month_dates:
        await session.execute(
            delete(SalesMonthly).where(
                and_(
                    SalesMonthly.store_id == store_id,
                    SalesMonthly.month_start.in_(month_dates),
                )
            )
        )

    await session.execute(
        sql_text(
            """
            INSERT INTO sales_monthly (
                store_id,
                article,
                month_start,
                qty,
                unit,
                refreshed_at
            )
            SELECT
                sl.store_id,
                sl.article,
                (DATE_TRUNC('month', sl.sold_at AT TIME ZONE 'UTC'))::date AS month_start,
                SUM(sl.qty) AS qty,
                COALESCE(MAX(NULLIF(TRIM(sl.unit), '')), '') AS unit,
                :now_ts
            FROM sale_line sl
            WHERE sl.store_id = :store_id
              AND sl.sold_at >= :overall_from
              AND sl.sold_at < :overall_to_exclusive
            GROUP BY sl.store_id, sl.article,
                (DATE_TRUNC('month', sl.sold_at AT TIME ZONE 'UTC'))::date
            """
        ),
        {
            "store_id": store_id,
            "overall_from": overall_from,
            "overall_to_exclusive": overall_to_exclusive,
            "now_ts": now,
        },
    )


async def sync_sales(
    session: AsyncSession,
    client: SabyClient,
    store_id: int,
    slices: list[MonthSlice],
    *,
    restrict_to_existing_products: bool = False,
) -> int:
    """Помесячная загрузка заказов: для каждого календарного месяца — отдельные запросы к Saby.

    Для каждого месяца: DELETE sale_line за интервал затем INSERT; в конце
    перестраиваются строки ``sales_monthly`` для охваченных месяцевов.

    При ``restrict_to_existing_products=True`` строки чеков с артикулами вне ``product``
    отбрасываются, upsert ``product`` из чеков не выполняется.
    """

    if not slices:
        return 0

    allowed_articles: set[str] | None = None
    if restrict_to_existing_products:
        rows = (
            await session.execute(
                select(Product.article).where(Product.article.isnot(None))
            )
        ).all()
        allowed_articles = {str(a[0]).strip() for a in rows if a[0]}

    overall_from = slices[0].start
    overall_to_exclusive = slices[-1].end_exclusive
    month_dates = month_starts_from_slices(slices)
    now = datetime.now(timezone.utc)
    sale_lines_total = 0

    for start, end_exc in slices:
        sale_lines_total += await _sync_sales_window(
            session=session,
            client=client,
            store_id=store_id,
            from_datetime=start,
            to_datetime=end_exc,
            shared_now=now,
            allowed_articles=allowed_articles,
            upsert_products=not restrict_to_existing_products,
        )

    await refresh_sales_monthly_for_store(
        session,
        store_id,
        overall_from,
        overall_to_exclusive,
        month_dates,
        now=now,
    )

    return sale_lines_total


async def _sync_sales_window(
    session: AsyncSession,
    client: SabyClient,
    store_id: int,
    from_datetime: datetime,
    to_datetime: datetime,
    *,
    shared_now: datetime,
    allowed_articles: set[str] | None = None,
    upsert_products: bool = True,
) -> int:
    if to_datetime <= from_datetime:
        raise ValueError("to_datetime must be strictly greater than from_datetime")

    resolver = await _build_nom_number_resolver(session)
    product_rows: dict[str, dict[str, Any]] = {}
    sale_rows: list[dict[str, Any]] = []

    page = 0
    while True:
        raw = await client.list_sales(
            from_datetime=from_datetime,
            to_datetime=to_datetime,
            point_id=store_id,
            page=page,
            page_size=_PAGE_SIZE,
        )
        orders = iter_order_dicts(raw)
        if not orders:
            break

        for order in orders:
            try:
                ord_payload = RetailOrderPayload.model_validate(order)
            except ValidationError:
                logger.warning(
                    "Skipping order with invalid payload for store %s", store_id
                )
                continue
            order_sold_at = (
                _parse_order_datetime_payload(ord_payload) or from_datetime
            )
            order_id = _stringify(ord_payload.id or ord_payload.orderId or ord_payload.uuid)
            lines = _validated_lines_from_payload(ord_payload)
            for line_no, line in enumerate(lines, start=1):
                raw_key = (line.article or "").strip()
                if not raw_key:
                    continue
                article = resolver.get(raw_key, raw_key)
                if allowed_articles is not None and article not in allowed_articles:
                    continue
                name = line.name or ""
                unit_val = line.unit or ""
                qty = to_decimal(line.count)
                if line.is_return is True:
                    qty = -abs(qty)
                if upsert_products:
                    product_rows.setdefault(
                        article,
                        {
                            "article": article,
                            "name": name,
                            "unit": unit_val,
                            "updated_at": shared_now,
                            "nom_number": None,
                        },
                    )
                sale_rows.append(
                    {
                        "store_id": store_id,
                        "article": article,
                        "sold_at": order_sold_at,
                        "qty": qty,
                        "unit": unit_val,
                        "external_order_id": order_id,
                        "line_no": line_no,
                    }
                )

        outcome = raw.get("outcome") or raw.get("outCome") or {}
        has_more = outcome.get("hasMore")
        if has_more is False:
            break
        if has_more is None and len(orders) == 0:
            break
        page += 1

    if upsert_products and product_rows:
        stmt = pg_insert(Product).values(list(product_rows.values()))
        stmt = stmt.on_conflict_do_update(
            index_elements=[Product.article],
            set_={
                "name": stmt.excluded.name,
                "unit": stmt.excluded.unit,
                "updated_at": shared_now,
                "nom_number": func.coalesce(Product.nom_number, stmt.excluded.nom_number),
                "type": func.coalesce(
                    func.nullif(Product.type, ""),
                    stmt.excluded.type,
                ),
                "focus": func.coalesce(
                    func.nullif(Product.focus, ""),
                    stmt.excluded.focus,
                ),
                "group_abc": func.coalesce(
                    func.nullif(Product.group_abc, ""),
                    stmt.excluded.group_abc,
                ),
                "feature": func.coalesce(
                    func.nullif(Product.feature, ""),
                    stmt.excluded.feature,
                ),
                "quantity_in_box": case(
                    (stmt.excluded.quantity_in_box > 0, stmt.excluded.quantity_in_box),
                    else_=Product.quantity_in_box,
                ),
            },
        )
        await session.execute(stmt)

    await session.execute(
        delete(SaleLine).where(
            and_(
                SaleLine.store_id == store_id,
                SaleLine.sold_at >= from_datetime,
                SaleLine.sold_at < to_datetime,
            )
        )
    )

    if sale_rows:
        chunk_size = 1000
        for i in range(0, len(sale_rows), chunk_size):
            await session.execute(insert(SaleLine).values(sale_rows[i : i + chunk_size]))

    return len(sale_rows)


def _validated_lines_from_payload(payload: RetailOrderPayload) -> list[OrderLinePayload]:
    lines: list[OrderLinePayload] = []
    for raw in payload.order_lines_raw():
        try:
            lines.append(OrderLinePayload.model_validate(raw))
        except ValidationError:
            continue
    return lines


def _parse_order_datetime_payload(order: RetailOrderPayload) -> datetime | None:
    for raw in (
        order.dateTime,
        order.date_time,
        order.date_time_iso,
        order.date,
        order.createdAt,
        order.created_at,
    ):
        if raw is None or raw == "":
            continue
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        if isinstance(raw, str):
            text = raw.strip()
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
    return None


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
