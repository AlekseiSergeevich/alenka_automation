from __future__ import annotations

import enum
import logging
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.backend.app.core.config import Settings, get_settings
from src.backend.app.db.session import get_sessionmaker
from src.backend.app.ingestion import sync_points, sync_sales, sync_stock
from src.backend.app.integrations.saby.client import SabyClient
from src.backend.app.models import Store, SyncEntity, SyncRun, SyncStatus
from src.backend.app.services.aggregate import refresh_aggregate

logger = logging.getLogger(__name__)


class TriggerMode(str, enum.Enum):
    auto = "auto"
    force = "force"


@dataclass(slots=True)
class FreshnessInfo:
    entity: SyncEntity
    store_id: int | None
    last_finished_at: datetime | None
    stale: bool
    ttl_seconds: int


def _advisory_lock_key(entity: SyncEntity, store_id: int | None) -> int:
    """Stable 64-bit key derived from entity + store id for pg_advisory_xact_lock."""

    token = f"{entity.value}:{store_id or 0}".encode()
    # crc32 is 32 bits; shift into signed bigint range so pg is happy.
    return zlib.crc32(token) - (1 << 31)


class SyncOrchestrator:
    """Coordinates TTL checks, locking and ingestion pipeline execution."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        client: SabyClient,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._client = client
        self._settings = settings

    # ---------- Public API ----------

    async def freshness(
        self, entity: SyncEntity, store_id: int | None = None
    ) -> FreshnessInfo:
        async with self._session_factory() as session:
            last = await self._last_success(session, entity, store_id)
        ttl = self._ttl_for(entity)
        stale = last is None or (
            datetime.now(timezone.utc) - last > timedelta(seconds=ttl)
        )
        return FreshnessInfo(
            entity=entity,
            store_id=store_id,
            last_finished_at=last,
            stale=stale,
            ttl_seconds=ttl,
        )

    async def ensure_fresh(
        self,
        entity: SyncEntity,
        store_id: int | None = None,
        background_tasks: BackgroundTasks | None = None,
        mode: TriggerMode = TriggerMode.auto,
    ) -> FreshnessInfo:
        """Check freshness; if stale, schedule or run the sync.

        - `mode=auto`: if stale, schedule a background task (fire-and-forget)
          and return immediately. Caller keeps serving current (stale) data.
        - `mode=force`: run synchronously regardless of TTL.
        """

        info = await self.freshness(entity, store_id)
        if mode == TriggerMode.force:
            await self.run(entity, store_id)
            return await self.freshness(entity, store_id)

        if info.stale and background_tasks is not None:
            background_tasks.add_task(self._safe_run, entity, store_id)
        elif info.stale:
            await self.run(entity, store_id)
            return await self.freshness(entity, store_id)

        return info

    async def ensure_overview_fresh(
        self, background_tasks: BackgroundTasks | None = None
    ) -> list[FreshnessInfo]:
        """Convenience: triggers points + stock + sales for all known stores."""

        infos: list[FreshnessInfo] = []
        infos.append(await self.ensure_fresh(SyncEntity.points, None, background_tasks))

        store_ids = await self._known_store_ids()
        for sid in store_ids:
            infos.append(
                await self.ensure_fresh(SyncEntity.stock, sid, background_tasks)
            )
            infos.append(
                await self.ensure_fresh(SyncEntity.sales, sid, background_tasks)
            )
        return infos

    async def run(self, entity: SyncEntity, store_id: int | None = None) -> SyncRun:
        """Run ingestion synchronously with advisory lock + aggregate refresh."""

        return await self._run_locked(entity, store_id)

    # ---------- Internals ----------

    async def _safe_run(self, entity: SyncEntity, store_id: int | None) -> None:
        try:
            await self._run_locked(entity, store_id)
        except Exception:
            logger.exception(
                "Background sync failed: entity=%s store_id=%s", entity, store_id
            )

    async def _run_locked(
        self, entity: SyncEntity, store_id: int | None
    ) -> SyncRun:
        lock_key = _advisory_lock_key(entity, store_id)
        now = datetime.now(timezone.utc)

        async with self._session_factory() as session:
            # One big transaction: advisory lock lives for the txn, ingestion
            # and aggregate refresh are committed together, and on failure we
            # still record a failed SyncRun in a fresh session.
            try:
                async with session.begin():
                    got = await session.scalar(
                        select(func.pg_try_advisory_xact_lock(lock_key))
                    )
                    if not got:
                        logger.info(
                            "Skipping sync, lock held: entity=%s store_id=%s",
                            entity,
                            store_id,
                        )
                        return await self._record_skipped(entity, store_id)

                    run = SyncRun(
                        entity=entity,
                        store_id=store_id,
                        started_at=now,
                        status=SyncStatus.running,
                    )
                    session.add(run)
                    await session.flush()

                    rows, cursor_from, cursor_to = await self._dispatch(
                        session, entity, store_id
                    )

                    await refresh_aggregate(session, store_id=store_id)

                    run.status = SyncStatus.success
                    run.finished_at = datetime.now(timezone.utc)
                    run.rows_upserted = rows
                    run.cursor_from = cursor_from
                    run.cursor_to = cursor_to

                    logger.info(
                        "sync_run completed",
                        extra={
                            "sync_run_id": run.id,
                            "entity": entity.value,
                            "store_id": store_id,
                            "rows_upserted": rows,
                        },
                    )

                    return run
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Sync failed: entity=%s store_id=%s", entity, store_id
                )
                await self._record_failed(entity, store_id, exc)
                raise

    async def _dispatch(
        self,
        session: AsyncSession,
        entity: SyncEntity,
        store_id: int | None,
    ) -> tuple[int, datetime | None, datetime | None]:
        if entity == SyncEntity.points:
            rows = await sync_points(session, self._client)
            return rows, None, None

        if store_id is None:
            raise ValueError(f"{entity.value} sync requires store_id")

        if entity == SyncEntity.stock:
            rows = await sync_stock(session, self._client, store_id)
            return rows, None, None

        if entity == SyncEntity.sales:
            from_dt, to_dt = await self._compute_sales_window(session, store_id)
            rows = await sync_sales(
                session, self._client, store_id, from_dt, to_dt
            )
            return rows, from_dt, to_dt

        raise ValueError(f"Unknown entity: {entity}")

    async def _compute_sales_window(
        self, session: AsyncSession, store_id: int
    ) -> tuple[datetime, datetime]:
        last_cursor = await session.scalar(
            select(SyncRun.cursor_to)
            .where(
                SyncRun.entity == SyncEntity.sales,
                SyncRun.store_id == store_id,
                SyncRun.status == SyncStatus.success,
                SyncRun.cursor_to.is_not(None),
            )
            .order_by(desc(SyncRun.finished_at))
            .limit(1)
        )
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=self._settings.sales_window_days)
        if last_cursor is None:
            return window_start, now
        overlap = timedelta(days=self._settings.sales_sync_overlap_days)
        from_dt = max(window_start, last_cursor - overlap)
        if from_dt >= now:
            from_dt = now - timedelta(minutes=1)
        return from_dt, now

    async def _last_success(
        self,
        session: AsyncSession,
        entity: SyncEntity,
        store_id: int | None,
    ) -> datetime | None:
        conditions = [
            SyncRun.entity == entity,
            SyncRun.status == SyncStatus.success,
        ]
        if store_id is None:
            conditions.append(SyncRun.store_id.is_(None))
        else:
            conditions.append(SyncRun.store_id == store_id)
        return await session.scalar(
            select(func.max(SyncRun.finished_at)).where(*conditions)
        )

    async def _known_store_ids(self) -> list[int]:
        async with self._session_factory() as session:
            result = await session.execute(select(Store.id).order_by(Store.id))
            return [row for row in result.scalars().all()]

    def _ttl_for(self, entity: SyncEntity) -> int:
        mapping = {
            SyncEntity.points: self._settings.ttl_points_seconds,
            SyncEntity.stock: self._settings.ttl_stock_seconds,
            SyncEntity.sales: self._settings.ttl_sales_seconds,
        }
        return mapping[entity]

    async def _record_skipped(
        self, entity: SyncEntity, store_id: int | None
    ) -> SyncRun:
        async with self._session_factory() as session:
            async with session.begin():
                run = SyncRun(
                    entity=entity,
                    store_id=store_id,
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                    status=SyncStatus.failed,
                    error="lock_held",
                )
                session.add(run)
                await session.flush()
                return run

    async def _record_failed(
        self, entity: SyncEntity, store_id: int | None, exc: BaseException
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                run = SyncRun(
                    entity=entity,
                    store_id=store_id,
                    started_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                    status=SyncStatus.failed,
                    error=str(exc)[:4000],
                )
                session.add(run)


def build_orchestrator(client: SabyClient) -> SyncOrchestrator:
    return SyncOrchestrator(
        session_factory=get_sessionmaker(),
        client=client,
        settings=get_settings(),
    )
