import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.app.integrations.saby.client import SabyClient
from src.backend.app.integrations.saby.schemas import PointSchema, iter_sales_point_dicts
from src.backend.app.models import Store

logger = logging.getLogger(__name__)

_PAGE_SIZE = 200


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
        if batch:
            stmt = pg_insert(Store).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Store.id],
                set_={
                    "name": stmt.excluded.name,
                    "address": stmt.excluded.address,
                    "locality": stmt.excluded.locality,
                    "prices": stmt.excluded.prices,
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
                "prices": list(point.prices or []),
                "raw": item,
                "first_seen_at": now,
                "updated_at": now,
            }
        )
    return rows
