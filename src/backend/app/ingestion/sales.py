import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, delete, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.app.ingestion.utils import extract_items, to_decimal
from src.backend.app.integrations.saby.client import SabyClient
from src.backend.app.models import Product, SaleLine

logger = logging.getLogger(__name__)

_PAGE_SIZE = 200


async def sync_sales(
    session: AsyncSession,
    client: SabyClient,
    store_id: int,
    from_datetime: datetime,
    to_datetime: datetime,
) -> int:
    """Replace `sale_line` rows for a store in the `[from, to)` window.

    Uses the DELETE-window + INSERT idempotency strategy described in the plan
    since Saby order lines do not expose a stable line identifier. This is
    safe because Saby is the source of truth for the window.
    """

    if to_datetime <= from_datetime:
        raise ValueError("to_datetime must be strictly greater than from_datetime")

    now = datetime.now(timezone.utc)
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
        orders = extract_items(raw)
        if not orders:
            break

        for order in orders:
            order_sold_at = _parse_order_datetime(order) or from_datetime
            order_id = _stringify(order.get("id") or order.get("orderId") or order.get("uuid"))
            lines = _extract_order_lines(order)
            for line_no, line in enumerate(lines, start=1):
                article = _stringify(line.get("article"))
                if not article:
                    continue
                name = str(line.get("name") or "")
                unit = str(line.get("unit") or "")
                qty = to_decimal(line.get("count"))
                product_rows.setdefault(
                    article,
                    {
                        "article": article,
                        "name": name,
                        "unit": unit,
                        "updated_at": now,
                    },
                )
                sale_rows.append(
                    {
                        "store_id": store_id,
                        "article": article,
                        "sold_at": order_sold_at,
                        "qty": qty,
                        "unit": unit,
                        "external_order_id": order_id,
                        "line_no": line_no,
                    }
                )

        if len(orders) < _PAGE_SIZE:
            break
        page += 1

    if product_rows:
        stmt = pg_insert(Product).values(list(product_rows.values()))
        stmt = stmt.on_conflict_do_update(
            index_elements=[Product.article],
            set_={
                "name": stmt.excluded.name,
                "unit": stmt.excluded.unit,
                "updated_at": now,
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
        # Chunk the insert to keep parameter counts reasonable.
        chunk_size = 1000
        for i in range(0, len(sale_rows), chunk_size):
            await session.execute(insert(SaleLine).values(sale_rows[i : i + chunk_size]))

    return len(sale_rows)


_ORDER_LINE_KEYS: tuple[str, ...] = (
    "nomenclatures",
    "items",
    "positions",
    "lines",
    "products",
)

_ORDER_TIMESTAMP_KEYS: tuple[str, ...] = (
    "dateTime",
    "date_time",
    "datetime",
    "date",
    "createdAt",
    "created_at",
)


def _extract_order_lines(order: dict[str, Any]) -> list[dict[str, Any]]:
    for key in _ORDER_LINE_KEYS:
        value = order.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def _parse_order_datetime(order: dict[str, Any]) -> datetime | None:
    for key in _ORDER_TIMESTAMP_KEYS:
        raw = order.get(key)
        if not raw:
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
