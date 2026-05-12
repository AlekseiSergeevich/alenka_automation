from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from src.backend.app.api.deps import get_orchestrator, require_admin, require_user
from src.backend.app.core.config import Settings, get_settings
from src.backend.app.models import SyncEntity
from src.backend.app.services import FreshnessInfo, SyncOrchestrator, TriggerMode
from src.backend.app.services.startup_bootstrap import run_startup_bootstrap

router = APIRouter()


@router.post(
    "/sync/bootstrap",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)],
)
async def bootstrap_sync(
    mode: TriggerMode = Query(
        default=TriggerMode.force,
        description="Сейчас поддерживается только force (синхронное выполнение).",
    ),
    orchestrator: SyncOrchestrator = Depends(get_orchestrator),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Точки → для каждой точки склад и продажи (помесячно за N месяцев)."""

    if mode != TriggerMode.force:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bootstrap-sync currently requires mode=force",
        )

    summary = await orchestrator.bootstrap_all_sync()
    summary["months_back"] = settings.sales_months_back
    summary["detail"] = "Bootstrap completed."
    return summary


@router.post(
    "/sync/bootstrap-safe",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)],
)
async def bootstrap_safe_sync(
    order_blank: str | None = Query(
        default=None,
        description="Необязательный путь к .xls бланка; иначе из настроек или авто-поиск в data/raw.",
    ),
    orchestrator: SyncOrchestrator = Depends(get_orchestrator),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Безопасный bootstrap: точки → seed бланка при пустом product → склад/продажи без расширения каталога."""

    blank_path = Path(order_blank).expanduser() if order_blank else None
    summary = await run_startup_bootstrap(
        orchestrator,
        settings,
        order_blank_path=blank_path,
    )
    summary["months_back"] = settings.sales_months_back
    summary["detail"] = "Safe bootstrap finished."
    return summary


@router.post(
    "/sync/{entity}",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_admin)],
)
async def trigger_sync(
    entity: SyncEntity,
    background_tasks: BackgroundTasks,
    store_id: int | None = Query(default=None, description="Required for stock and sales."),
    mode: TriggerMode = Query(default=TriggerMode.auto),
    orchestrator: SyncOrchestrator = Depends(get_orchestrator),
) -> dict[str, object]:
    """Trigger an ingestion run.

    `mode=auto` schedules a background task when data is stale and returns
    current freshness; `mode=force` runs the sync synchronously regardless of
    TTL and returns the updated freshness.
    """

    if entity in (SyncEntity.stock, SyncEntity.sales) and store_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"store_id is required for {entity.value} sync",
        )
    info = await orchestrator.ensure_fresh(
        entity=entity,
        store_id=store_id,
        background_tasks=background_tasks,
        mode=mode,
    )
    return {
        "entity": info.entity.value,
        "store_id": info.store_id,
        "last_finished_at": info.last_finished_at,
        "stale": info.stale,
        "ttl_seconds": info.ttl_seconds,
        "mode": mode.value,
    }


@router.get("/sync/status", dependencies=[Depends(require_user)])
async def sync_status(
    orchestrator: SyncOrchestrator = Depends(get_orchestrator),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    """Return freshness for points + stock/sales for every known store."""

    infos: list[dict[str, Any]] = []

    pinfo = await orchestrator.freshness(SyncEntity.points, None)
    infos.append(
        _freshness_to_dict(
            pinfo,
            extra={"sales_months_back": settings.sales_months_back},
        )
    )

    for sid in await orchestrator.known_store_ids():
        for entity in (SyncEntity.stock, SyncEntity.sales):
            info = await orchestrator.freshness(entity, sid)
            extra: dict[str, Any] = {"sales_months_back": settings.sales_months_back}
            if entity == SyncEntity.sales:
                extra["month_coverage"] = await orchestrator.sales_month_coverage(sid)
            infos.append(_freshness_to_dict(info, extra=extra))

    return infos


def _freshness_to_dict(
    info: FreshnessInfo,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "entity": info.entity.value,
        "store_id": info.store_id,
        "last_finished_at": info.last_finished_at,
        "stale": info.stale,
        "ttl_seconds": info.ttl_seconds,
    }
    if extra:
        payload.update(extra)
    return payload
