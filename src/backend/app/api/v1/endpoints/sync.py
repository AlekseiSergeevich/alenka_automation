from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from src.backend.app.api.deps import get_orchestrator
from src.backend.app.models import SyncEntity
from src.backend.app.services import SyncOrchestrator, TriggerMode

router = APIRouter()


@router.post("/sync/{entity}", status_code=status.HTTP_202_ACCEPTED)
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


@router.get("/sync/status")
async def sync_status(
    orchestrator: SyncOrchestrator = Depends(get_orchestrator),
) -> list[dict[str, object]]:
    """Return freshness for points + stock/sales for every known store."""

    infos = []
    for entity in (SyncEntity.points,):
        info = await orchestrator.freshness(entity, None)
        infos.append(_freshness_to_dict(info))
    for sid in await orchestrator._known_store_ids():  # noqa: SLF001 (admin readout)
        for entity in (SyncEntity.stock, SyncEntity.sales):
            info = await orchestrator.freshness(entity, sid)
            infos.append(_freshness_to_dict(info))
    return infos


def _freshness_to_dict(info) -> dict[str, object]:
    return {
        "entity": info.entity.value,
        "store_id": info.store_id,
        "last_finished_at": info.last_finished_at,
        "stale": info.stale,
        "ttl_seconds": info.ttl_seconds,
    }
