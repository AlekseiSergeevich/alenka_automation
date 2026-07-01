"""Полная синхронизация справочника ``product`` из распарсенного бланка заказа."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.app.models import OrderBlankUpload, Product

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_month_start(when: datetime | None = None) -> datetime:
    dt = when or utc_now()
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def product_row_count(session: AsyncSession) -> int:
    n = await session.scalar(select(func.count()).select_from(Product))
    return int(n or 0)


async def apply_order_blank_full_sync(
    session: AsyncSession,
    product_rows: list[dict[str, Any]],
    articles: list[str],
    *,
    now: datetime | None = None,
) -> int:
    """Upsert всех позиций из бланка, затем удаление артикулов, которых нет в файле.

    Возвращает число строк в ``product_rows`` (после дедупликации — длина списка).
    """
    if not articles:
        raise ValueError("articles must be non-empty")

    ts = now or utc_now()
    clean_rows = []
    for row in product_rows:
        clean_rows.append({
            "article": row["article"],
            "nom_number": row.get("nom_number"),
            "name": row["name"],
            "unit": row["unit"],
            "type": row["type"],
            "focus": row["focus"],
            "group_abc": row["group_abc"],
            "feature": row["feature"],
            "quantity_in_box": row["quantity_in_box"],
            "updated_at": ts,
        })

    stmt = pg_insert(Product).values(clean_rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Product.article],
        set_={
            "name": stmt.excluded.name,
            "unit": stmt.excluded.unit,
            "type": stmt.excluded.type,
            "focus": stmt.excluded.focus,
            "group_abc": stmt.excluded.group_abc,
            "feature": stmt.excluded.feature,
            "quantity_in_box": stmt.excluded.quantity_in_box,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    await session.execute(stmt)
    await session.execute(delete(Product).where(Product.article.not_in(articles)))
    return len(product_rows)


async def fetch_last_successful_upload(session: AsyncSession) -> OrderBlankUpload | None:
    return (
        await session.execute(
            select(OrderBlankUpload)
            .where(
                OrderBlankUpload.status == STATUS_SUCCESS,
                OrderBlankUpload.applied_at.isnot(None),
            )
            .order_by(OrderBlankUpload.applied_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def has_successful_upload_in_current_month(
    session: AsyncSession,
    *,
    reference: datetime | None = None,
) -> bool:
    start = utc_month_start(reference)
    row = (
        await session.execute(
            select(OrderBlankUpload.id)
            .where(
                OrderBlankUpload.status == STATUS_SUCCESS,
                OrderBlankUpload.applied_at.isnot(None),
                OrderBlankUpload.applied_at >= start,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return row is not None


@dataclass(slots=True)
class OrderBlankReminderState:
    product_count: int
    catalog_empty: bool
    #: Нет успешной загрузки бланка в текущем UTC-месяце (или успешных записей ещё не было).
    needs_monthly_upload: bool
    last_success_applied_at: datetime | None

    @property
    def needs_order_blank_attention(self) -> bool:
        return self.catalog_empty or self.needs_monthly_upload


async def compute_order_blank_reminder_state(session: AsyncSession) -> OrderBlankReminderState:
    n = await product_row_count(session)
    catalog_empty = n == 0
    try:
        last = await fetch_last_successful_upload(session)
        applied = last.applied_at if last else None
        ok_month = await has_successful_upload_in_current_month(session)
        needs_monthly = not ok_month
    except ProgrammingError:
        # Таблица ещё не создана (миграция не применена) — не ломаем overview.
        await session.rollback()
        applied = None
        needs_monthly = False
    return OrderBlankReminderState(
        product_count=n,
        catalog_empty=catalog_empty,
        needs_monthly_upload=needs_monthly,
        last_success_applied_at=applied,
    )
