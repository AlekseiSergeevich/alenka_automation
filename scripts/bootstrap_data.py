#!/usr/bin/env python3
"""CLI: безопасная загрузка точек, бланка заказа и фактов (склад/продажи).

Примеры:
  python scripts/bootstrap_data.py --all
  python scripts/bootstrap_data.py --stores-only
  python scripts/bootstrap_data.py --facts-only --order-blank data/raw/....xls
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select  # noqa: E402

from src.backend.app.core.config import get_settings  # noqa: E402
from src.backend.app.db.session import get_sessionmaker  # noqa: E402
from src.backend.app.ingestion.order_blank import seed_products_from_order_blank_if_empty  # noqa: E402
from src.backend.app.integrations.saby.client import SabyClient  # noqa: E402
from src.backend.app.models import Product, SyncEntity  # noqa: E402
from src.backend.app.services.orchestrator import (  # noqa: E402
    build_orchestrator,
    catalog_safe_ingestion,
)
from src.backend.app.services.startup_bootstrap import run_startup_bootstrap  # noqa: E402


async def _cmd_stores_only() -> dict[str, object]:
    settings = get_settings()
    if not settings.saby_is_configured:
        return {"error": "saby_not_configured"}
    client = SabyClient(settings=settings)
    orch = build_orchestrator(client)
    await orch.run(SyncEntity.points, None)
    return {"status": "ok", "mode": "stores-only"}


async def _cmd_facts_only(order_blank: Path | None) -> dict[str, object]:
    settings = get_settings()
    if not settings.saby_is_configured:
        return {"error": "saby_not_configured"}

    factory = get_sessionmaker()
    async with factory() as session:
        async with session.begin():
            seed = await seed_products_from_order_blank_if_empty(
                session,
                order_blank,
                project_root=ROOT,
            )

    async with factory() as session:
        n = await session.scalar(select(func.count()).select_from(Product))

    if int(n or 0) == 0:
        return {
            "status": "needs_order_blank",
            "order_blank_seed": seed.status.value,
        }

    client = SabyClient(settings=settings)
    orch = build_orchestrator(client)
    token = catalog_safe_ingestion.set(True)
    try:
        ids = await orch.known_store_ids()
        for sid in ids:
            await orch.run(SyncEntity.stock, sid)
            await orch.run(SyncEntity.sales, sid)
    finally:
        catalog_safe_ingestion.reset(token)

    return {
        "status": "ok",
        "mode": "facts-only",
        "order_blank_seed": seed.status.value,
        "stores_synced": len(ids),
    }


async def _cmd_all(order_blank: Path | None) -> dict[str, object]:
    settings = get_settings()
    client = SabyClient(settings=settings)
    orch = build_orchestrator(client)
    return await run_startup_bootstrap(
        orch,
        settings,
        order_blank_path=order_blank,
    )


async def _async_main(args: argparse.Namespace) -> int:
    if args.stores_only:
        out = await _cmd_stores_only()
    elif args.facts_only:
        out = await _cmd_facts_only(args.order_blank)
    else:
        out = await _cmd_all(args.order_blank)

    print(out)

    if out.get("error") == "saby_not_configured":
        return 1 if args.strict else 0
    if out.get("status") == "needs_order_blank":
        return 1 if args.strict else 0
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--all",
        action="store_true",
        help="Точки → бланк (если product пустой) → остатки и продажи (по умолчанию).",
    )
    mode.add_argument(
        "--stores-only",
        action="store_true",
        help="Только список точек Saby в таблицу store.",
    )
    mode.add_argument(
        "--facts-only",
        "--facts",
        dest="facts_only",
        action="store_true",
        help="Только бланк (если нужен) и загрузка остатков/продаж по известным точкам.",
    )
    p.add_argument(
        "--order-blank",
        type=Path,
        default=None,
        help="Путь к .xls бланка заказа (иначе авто-поиск в data/raw).",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Ненулевой код выхода при needs_order_blank или отсутствии Saby.",
    )
    args = p.parse_args()
    if not args.stores_only and not args.facts_only and not args.all:
        args.all = True

    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
