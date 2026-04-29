import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import and_, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.app.ingestion.utils import extract_items, to_decimal
from src.backend.app.integrations.saby.client import SabyClient
from src.backend.app.integrations.saby.schemas import ProductBalanceScema
from src.backend.app.models import Product, StockCurrent

logger = logging.getLogger(__name__)

_PAGE_SIZE = 500


async def sync_stock(
    session: AsyncSession,
    client: SabyClient,
    store_id: int,
) -> int:
    """Refresh `stock_current` and `product` for a single store.

    Pulls all nomenclature items with `withBalance=true`, upserts the product
    dictionary and replaces the store's current stock snapshot transactionally.
    Removed SKUs are deleted so that `agg_store_product` does not carry stale
    rows.
    """

    now = datetime.now(timezone.utc)
    seen_articles: set[str] = set()
    product_rows: list[dict[str, Any]] = []
    stock_rows: list[dict[str, Any]] = []

    page = 0
    while True:
        raw = await client.list_products(
            point_id=store_id,
            with_balance=True,
            page=page,
            page_size=_PAGE_SIZE,
        )
        items = extract_items(raw)
        if not items:
            break

        for item in items:
            try:
                entry = ProductBalanceScema.model_validate(item)
            except ValidationError:
                logger.warning(
                    "Skipping stock row with invalid payload for store %s: %s",
                    store_id,
                    item.get("article"),
                )
                continue
            if not entry.article:
                continue
            if entry.article in seen_articles:
                # Defensive dedup in case Saby returns duplicates across pages.
                continue
            seen_articles.add(entry.article)
            product_rows.append(
                {
                    "article": entry.article,
                    "name": entry.name or "",
                    "unit": entry.unit or "",
                    "updated_at": now,
                }
            )
            stock_rows.append(
                {
                    "store_id": store_id,
                    "article": entry.article,
                    "balance": to_decimal(entry.balance),
                    "captured_at": now,
                }
            )

        if len(items) < _PAGE_SIZE:
            break
        page += 1

    if product_rows:
        stmt = pg_insert(Product).values(product_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Product.article],
            set_={
                "name": stmt.excluded.name,
                "unit": stmt.excluded.unit,
                "updated_at": now,
            },
        )
        await session.execute(stmt)

    if stock_rows:
        stmt = pg_insert(StockCurrent).values(stock_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[StockCurrent.store_id, StockCurrent.article],
            set_={
                "balance": stmt.excluded.balance,
                "captured_at": stmt.excluded.captured_at,
            },
        )
        await session.execute(stmt)

    # Drop rows that disappeared from Saby's nomenclature for this store.
    if seen_articles:
        await session.execute(
            delete(StockCurrent).where(
                and_(
                    StockCurrent.store_id == store_id,
                    StockCurrent.article.notin_(seen_articles),
                )
            )
        )
    else:
        await session.execute(delete(StockCurrent).where(StockCurrent.store_id == store_id))

    return len(stock_rows)
