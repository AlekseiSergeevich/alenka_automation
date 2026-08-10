"""Безопасная первичная загрузка при старте: точки → бланк (если пустой ``product``) → факты."""

from __future__ import annotations

import logging
import zlib
from pathlib import Path
from typing import Any

from sqlalchemy import func, literal, select

from src.backend.app.core.config import Settings
from src.backend.app.db.session import get_engine
from src.backend.app.ingestion.order_blank import (
    project_root_from_here,
    seed_products_from_order_blank_if_empty,
)
from src.backend.app.models import Product, SyncEntity
from src.backend.app.services.orchestrator import SyncOrchestrator, catalog_safe_ingestion

logger = logging.getLogger(__name__)

# Отдельный ключ от SyncOrchestrator entity-locks (zlib crc32 → signed bigint).
_BOOTSTRAP_ADVISORY_KEY = zlib.crc32(b"candy_forecast:startup_bootstrap:v1") - (1 << 31)


async def run_startup_bootstrap(
    orchestrator: SyncOrchestrator,
    settings: Settings,
    *,
    order_blank_path: Path | None = None,
) -> dict[str, Any]:
    """Синхронизировать точки, при необходимости заполнить ``product`` из бланка, затем склад/продажи.

    Не падает при отсутствии файла бланка: ``product`` остаётся пустым, факты не грузятся.

    При ``startup_bootstrap_use_advisory_lock`` удерживается session advisory lock PostgreSQL,
    чтобы несколько uvicorn workers не выполняли полный bootstrap одновременно.
    """

    if settings.startup_bootstrap_use_advisory_lock:
        engine = get_engine()
        async with engine.connect() as conn:
            got = await conn.scalar(
                select(func.pg_try_advisory_lock(literal(_BOOTSTRAP_ADVISORY_KEY)))
            )
            if not got:
                logger.info("Startup bootstrap skipped: advisory lock held")
                return {"status": "skipped", "reason": "bootstrap_lock_held"}
            try:
                return await _run_startup_bootstrap_impl(
                    orchestrator,
                    settings,
                    order_blank_path=order_blank_path,
                )
            finally:
                await conn.execute(
                    select(func.pg_advisory_unlock(literal(_BOOTSTRAP_ADVISORY_KEY)))
                )

    return await _run_startup_bootstrap_impl(
        orchestrator,
        settings,
        order_blank_path=order_blank_path,
    )


async def _run_startup_bootstrap_impl(
    orchestrator: SyncOrchestrator,
    settings: Settings,
    *,
    order_blank_path: Path | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {"status": "ok"}

    if not settings.saby_is_configured:
        summary["status"] = "skipped"
        summary["reason"] = "saby_not_configured"
        logger.info("Startup bootstrap skipped: Saby not configured")
        return summary

    await orchestrator.run(SyncEntity.points, None)
    summary["points"] = "synced"

    blank_path = order_blank_path or settings.startup_bootstrap_order_blank_path
    root = project_root_from_here()

    factory = orchestrator._session_factory
    async with factory() as session:
        async with session.begin():
            seed_result = await seed_products_from_order_blank_if_empty(
                session,
                blank_path,
                project_root=root,
            )

    summary["order_blank_seed"] = seed_result.status.value
    if seed_result.path:
        summary["order_blank_path"] = str(seed_result.path)
    if seed_result.rows_inserted:
        summary["order_blank_rows_inserted"] = seed_result.rows_inserted

    async with factory() as session:
        n = await session.scalar(select(func.count()).select_from(Product))

    if int(n or 0) == 0:
        summary["status"] = "needs_order_blank"
        summary["reason"] = "product_empty"
        logger.info(
            "Startup bootstrap: product catalog empty; skipping stock/sales "
            "(load order blank or seed products separately)."
        )
        return summary

    if not settings.startup_bootstrap_load_facts:
        summary["facts"] = "skipped_by_settings"
        return summary

    token = catalog_safe_ingestion.set(True)
    try:
        ids = await orchestrator.known_store_ids()
        for sid in ids:
            await orchestrator.run(SyncEntity.stock, sid)
            await orchestrator.run(SyncEntity.sales, sid)
        summary["stores_synced"] = len(ids)
        summary["store_ids"] = ids
    finally:
        catalog_safe_ingestion.reset(token)

    return summary
