import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.app.integrations.saby.client import SabyClient
from src.backend.app.integrations.saby.schemas import (
    PointSchema,
    first_price_list_id,
    iter_sales_point_dicts,
)
from src.backend.app.models import Store

logger = logging.getLogger(__name__)

_PAGE_SIZE = 200
_PRICE_LIST_CONCURRENCY = 8


async def _fetch_first_price_list_id(client: SabyClient, point_id: int) -> int | None:
    try:
        raw = await client.price_list(
            point_id=point_id,
            actual_date=datetime.now(timezone.utc),
            page=0,
            page_size=100,
        )
        return first_price_list_id(raw)
    except Exception:
        logger.warning(
            "Не удалось получить price-list для точки %s; price_list_id останется пустым",
            point_id,
            exc_info=True,
        )
        return None


async def _attach_price_list_ids(client: SabyClient, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    sem = asyncio.Semaphore(_PRICE_LIST_CONCURRENCY)

    async def _one(row: dict[str, Any]) -> None:
        pid = row["id"]
        async with sem:
            plid = await _fetch_first_price_list_id(client, int(pid))
        row["price_list_id"] = plid

    await asyncio.gather(*(_one(r) for r in rows))


async def sync_points(session: AsyncSession, client: SabyClient) -> int:
    """Full refresh of the `store` table from Saby sales points.

    Returns the number of upserted rows.
    """

    total = 0
    page = 0
    while True:
        raw = await client.list_sales_points(page=page, page_size=_PAGE_SIZE)
        items = iter_sales_point_dicts(raw)
        if not items:
            break

        batch = _build_rows(items)
        await _attach_price_list_ids(client, batch)
        if batch:
            stmt = pg_insert(Store).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Store.id],
                set_={
                    "name": stmt.excluded.name,
                    "address": stmt.excluded.address,
                    "locality": stmt.excluded.locality,
                    "warehouse_id": stmt.excluded.warehouse_id,
                    "price_list_id": func.coalesce(
                        stmt.excluded.price_list_id, Store.price_list_id
                    ),
                    "raw": stmt.excluded.raw,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await session.execute(stmt)
            total += len(batch)

        if len(items) < _PAGE_SIZE:
            break
        page += 1

    return total


def _build_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for item in items:
        try:
            point = PointSchema.model_validate(item)
        except ValidationError:
            logger.warning("Skipping point with invalid payload: %s", item.get("id"))
            continue
        rows.append(
            {
                "id": point.id,
                "name": point.name,
                "address": point.address or "",
                "locality": point.locality or "",
                "warehouse_id": point.warehouse_id,
                "price_list_id": None,
                "raw": item,
                "first_seen_at": now,
                "updated_at": now,
            }
        )
    return rows
