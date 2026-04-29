from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.app.api.deps import get_orchestrator
from src.backend.app.db.session import get_session
from src.backend.app.models import AggStoreProduct, Store
from src.backend.app.services import SyncOrchestrator

router = APIRouter()


class AggRow(BaseModel):
    store_id: int
    article: str
    store_name: str
    product_name: str
    unit: str
    stock_balance: Decimal
    stock_captured_at: datetime | None = None
    sales_qty_30d: Decimal
    sales_qty_90d: Decimal
    sales_qty_window: Decimal
    avg_daily_qty: Decimal
    last_sale_at: datetime | None = None
    days_of_cover: Decimal | None = None
    refreshed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OverviewMeta(BaseModel):
    total: int
    limit: int
    offset: int
    stale: bool
    warning: str | None = None


class OverviewResponse(BaseModel):
    meta: OverviewMeta
    items: list[AggRow]


SortField = Literal[
    "store_id",
    "article",
    "product_name",
    "stock_balance",
    "sales_qty_30d",
    "sales_qty_90d",
    "sales_qty_window",
    "avg_daily_qty",
    "days_of_cover",
    "last_sale_at",
]


_SORT_COLUMNS = {
    "store_id": AggStoreProduct.store_id,
    "article": AggStoreProduct.article,
    "product_name": AggStoreProduct.product_name,
    "stock_balance": AggStoreProduct.stock_balance,
    "sales_qty_30d": AggStoreProduct.sales_qty_30d,
    "sales_qty_90d": AggStoreProduct.sales_qty_90d,
    "sales_qty_window": AggStoreProduct.sales_qty_window,
    "avg_daily_qty": AggStoreProduct.avg_daily_qty,
    "days_of_cover": AggStoreProduct.days_of_cover,
    "last_sale_at": AggStoreProduct.last_sale_at,
}


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    background_tasks: BackgroundTasks,
    store_id: int | None = Query(default=None),
    search: str | None = Query(default=None, description="Matches product name or article."),
    stock_gt: Decimal | None = Query(default=None, description="Return rows with stock_balance strictly greater than."),
    stock_lt: Decimal | None = Query(default=None),
    sort: SortField = Query(default="days_of_cover"),
    direction: Literal["asc", "desc"] = Query(default="asc"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    orchestrator: SyncOrchestrator = Depends(get_orchestrator),
) -> OverviewResponse:
    """Main user-facing table: store x product with stock + sales rollups.

    Triggers a background refresh of stale entities for all known stores but
    always serves the currently persisted snapshot. When nothing is persisted
    yet, the response is empty and `meta.stale=true`.
    """

    freshness = await orchestrator.ensure_overview_fresh(background_tasks)
    stale = any(info.stale for info in freshness)

    query = select(AggStoreProduct)
    filters = []
    if store_id is not None:
        filters.append(AggStoreProduct.store_id == store_id)
    if stock_gt is not None:
        filters.append(AggStoreProduct.stock_balance > stock_gt)
    if stock_lt is not None:
        filters.append(AggStoreProduct.stock_balance < stock_lt)
    if search:
        pattern = f"%{search.lower()}%"
        filters.append(
            or_(
                func.lower(AggStoreProduct.product_name).like(pattern),
                func.lower(AggStoreProduct.article).like(pattern),
            )
        )
    if filters:
        query = query.where(and_(*filters))

    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = await session.scalar(count_query) or 0

    sort_col = _SORT_COLUMNS[sort]
    order_clause = sort_col.asc() if direction == "asc" else sort_col.desc()
    query = query.order_by(order_clause, AggStoreProduct.store_id, AggStoreProduct.article)
    query = query.limit(limit).offset(offset)

    rows = (await session.execute(query)).scalars().all()

    return OverviewResponse(
        meta=OverviewMeta(
            total=int(total),
            limit=limit,
            offset=offset,
            stale=stale,
            warning=(
                "Data is being refreshed in the background; retry shortly for fresh values."
                if stale
                else None
            ),
        ),
        items=[AggRow.model_validate(row) for row in rows],
    )


class StoreSummary(BaseModel):
    id: int
    name: str
    address: str
    locality: str

    model_config = ConfigDict(from_attributes=True)


@router.get("/stores", response_model=list[StoreSummary])
async def list_stores(
    session: AsyncSession = Depends(get_session),
) -> list[StoreSummary]:
    rows = (await session.execute(select(Store).order_by(Store.id))).scalars().all()
    return [StoreSummary.model_validate(row) for row in rows]


@router.get("/stores/{store_id}/products", response_model=OverviewResponse)
async def list_store_products(
    store_id: int,
    background_tasks: BackgroundTasks,
    sort: SortField = Query(default="days_of_cover"),
    direction: Literal["asc", "desc"] = Query(default="asc"),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    orchestrator: SyncOrchestrator = Depends(get_orchestrator),
) -> OverviewResponse:
    store_exists = await session.scalar(
        select(func.count()).select_from(Store).where(Store.id == store_id)
    )
    if not store_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Store not found"
        )

    stock_info = await orchestrator.ensure_fresh(
        entity=_entity("stock"), store_id=store_id, background_tasks=background_tasks
    )
    sales_info = await orchestrator.ensure_fresh(
        entity=_entity("sales"), store_id=store_id, background_tasks=background_tasks
    )
    stale = stock_info.stale or sales_info.stale

    query = select(AggStoreProduct).where(AggStoreProduct.store_id == store_id)
    total = await session.scalar(
        select(func.count()).select_from(query.order_by(None).subquery())
    ) or 0
    sort_col = _SORT_COLUMNS[sort]
    order_clause = sort_col.asc() if direction == "asc" else sort_col.desc()
    rows = (
        await session.execute(
            query.order_by(order_clause, AggStoreProduct.article)
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    return OverviewResponse(
        meta=OverviewMeta(
            total=int(total),
            limit=limit,
            offset=offset,
            stale=stale,
            warning=(
                "Data is being refreshed in the background; retry shortly for fresh values."
                if stale
                else None
            ),
        ),
        items=[AggRow.model_validate(row) for row in rows],
    )


@router.get("/products/{article}", response_model=OverviewResponse)
async def product_across_stores(
    article: str,
    background_tasks: BackgroundTasks,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    orchestrator: SyncOrchestrator = Depends(get_orchestrator),
) -> OverviewResponse:
    """Cross-store view of a single article."""

    freshness = await orchestrator.ensure_overview_fresh(background_tasks)
    stale = any(info.stale for info in freshness)

    query = select(AggStoreProduct).where(AggStoreProduct.article == article)
    total = await session.scalar(
        select(func.count()).select_from(query.order_by(None).subquery())
    ) or 0
    rows = (
        await session.execute(
            query.order_by(AggStoreProduct.store_id).limit(limit).offset(offset)
        )
    ).scalars().all()

    return OverviewResponse(
        meta=OverviewMeta(
            total=int(total),
            limit=limit,
            offset=offset,
            stale=stale,
            warning=(
                "Data is being refreshed in the background; retry shortly for fresh values."
                if stale
                else None
            ),
        ),
        items=[AggRow.model_validate(row) for row in rows],
    )


def _entity(name: str):
    # Imported lazily to avoid module-level coupling for a single function.
    from src.backend.app.models import SyncEntity

    return SyncEntity(name)
