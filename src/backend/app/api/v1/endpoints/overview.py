from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from src.backend.app.api.deps import get_orchestrator, require_user
from src.backend.app.db.session import get_session
from src.backend.app.models import AggStoreProduct, Store
from src.backend.app.services import SyncOrchestrator
from src.backend.app.services.order_blank_catalog import compute_order_blank_reminder_state

router = APIRouter(dependencies=[Depends(require_user)])


class MonthlySalesBucket(BaseModel):
    month: date
    qty: Decimal
    orders_count: int = 0

    model_config = ConfigDict(extra="ignore")

    @field_validator("qty", mode="before")
    @classmethod
    def _coerce_qty(cls, v: Decimal | float | int | str) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))

    @field_validator("month", mode="before")
    @classmethod
    def _parse_month(cls, v: date | datetime | str) -> date:
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            head = v[:10].strip()
            y, mo, d = head.split("-", 2)
            return date(int(y), int(mo), int(d))
        raise TypeError("month field must be a date-compatible value")


class AggRow(BaseModel):
    store_id: int
    article: str
    store_name: str
    product_name: str
    rating: str
    unit: str
    stock_balance: Decimal
    stock_captured_at: datetime | None = None
    monthly_sales: list[MonthlySalesBucket]
    sales_qty_3m: Decimal
    avg_daily_qty: Decimal
    last_sale_at: datetime | None = None
    days_of_cover: Decimal | None = None
    refreshed_at: datetime

    model_config = ConfigDict(from_attributes=False)

    @classmethod
    def from_agg(cls, row: AggStoreProduct) -> AggRow:
        raw_monthly = getattr(row, "monthly_sales", None) or []
        buckets = [MonthlySalesBucket.model_validate(item) for item in raw_monthly]

        store_id = int(getattr(row, "store_id"))
        article = str(getattr(row, "article"))
        return cls(
            store_id=store_id,
            article=article,
            store_name=str(getattr(row, "store_name", "") or ""),
            product_name=str(getattr(row, "product_name", "") or ""),
            rating=str(getattr(getattr(row, "product", None), "focus", "") or ""),
            unit=str(getattr(row, "unit", "") or ""),
            stock_balance=Decimal(getattr(row, "stock_balance", 0)),
            stock_captured_at=getattr(row, "stock_captured_at", None),
            monthly_sales=buckets,
            sales_qty_3m=Decimal(getattr(row, "sales_qty_3m", 0)),
            avg_daily_qty=Decimal(getattr(row, "avg_daily_qty", 0)),
            last_sale_at=getattr(row, "last_sale_at", None),
            days_of_cover=(
                Decimal(getattr(row, "days_of_cover"))
                if getattr(row, "days_of_cover", None) is not None
                else None
            ),
            refreshed_at=getattr(row, "refreshed_at"),
        )


class OverviewMeta(BaseModel):
    total: int
    limit: int
    offset: int
    stale: bool
    warning: str | None = None
    #: Пустой каталог или не загружен бланок в текущем месяце.
    needs_order_blank: bool = False
    catalog_empty: bool = False
    needs_monthly_upload: bool = False
    last_order_blank_applied_at: datetime | None = None


class OverviewResponse(BaseModel):
    meta: OverviewMeta
    items: list[AggRow]


SortField = Literal[
    "store_id",
    "article",
    "product_name",
    "stock_balance",
    "sales_qty_3m",
    "avg_daily_qty",
    "days_of_cover",
    "last_sale_at",
]


_STALE_BG_WARNING = (
    "Данные обновляются в фоне — обновите страницу через минуту, "
    "чтобы получить актуальные значения."
)
_EMPTY_CATALOG_WARNING = (
    "Справочник товаров пуст; загрузите бланк заказа (.xls), чтобы включить "
    "синхронизацию остатков и продаж."
)
_MONTHLY_UPLOAD_WARNING = (
    "В текущем месяце ещё не загружен актуальный бланк заказа (.xls). "
    "Загрузите файл, чтобы обновить каталог."
)


def _overview_warning_meta(
    *,
    stale: bool,
    catalog_empty: bool,
    needs_monthly_upload: bool,
) -> str | None:
    if stale:
        return _STALE_BG_WARNING
    if catalog_empty:
        return _EMPTY_CATALOG_WARNING
    if needs_monthly_upload:
        return _MONTHLY_UPLOAD_WARNING
    return None


_SORT_COLUMNS = {
    "store_id": AggStoreProduct.store_id,
    "article": AggStoreProduct.article,
    "product_name": AggStoreProduct.product_name,
    "stock_balance": AggStoreProduct.stock_balance,
    "sales_qty_3m": AggStoreProduct.sales_qty_3m,
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
    """Основная таблица: магазин × товар, остатки и продажи по месяцам.

    Lazy refresh: при непустом каталоге ``product`` и устаревших TTL вызывается
    ``ensure_overview_fresh`` — фоновые задачи подтягивают точки/склад/продажи
    в catalog-safe режиме (без расширения справочника товаров из Saby).
    """

    hint = await compute_order_blank_reminder_state(session)
    freshness = await orchestrator.ensure_overview_fresh(background_tasks)
    stale = any(info.stale for info in freshness)

    query = select(AggStoreProduct).options(joinedload(AggStoreProduct.product))
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

    warn = _overview_warning_meta(
        stale=stale,
        catalog_empty=hint.catalog_empty,
        needs_monthly_upload=hint.needs_monthly_upload,
    )
    needs_attention = hint.needs_order_blank_attention

    return OverviewResponse(
        meta=OverviewMeta(
            total=int(total),
            limit=limit,
            offset=offset,
            stale=stale,
            needs_order_blank=needs_attention,
            catalog_empty=hint.catalog_empty,
            needs_monthly_upload=hint.needs_monthly_upload,
            last_order_blank_applied_at=hint.last_success_applied_at,
            warning=warn,
        ),
        items=[AggRow.from_agg(row) for row in rows],
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

    async with orchestrator.catalog_safe_overview_context():
        stock_info = await orchestrator.ensure_fresh(
            entity=_entity("stock"), store_id=store_id, background_tasks=background_tasks
        )
        sales_info = await orchestrator.ensure_fresh(
            entity=_entity("sales"), store_id=store_id, background_tasks=background_tasks
        )
    stale = stock_info.stale or sales_info.stale

    hint = await compute_order_blank_reminder_state(session)

    query = select(AggStoreProduct).options(joinedload(AggStoreProduct.product)).where(
        AggStoreProduct.store_id == store_id
    )
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

    warn = _overview_warning_meta(
        stale=stale,
        catalog_empty=hint.catalog_empty,
        needs_monthly_upload=hint.needs_monthly_upload,
    )

    return OverviewResponse(
        meta=OverviewMeta(
            total=int(total),
            limit=limit,
            offset=offset,
            stale=stale,
            warning=warn,
            needs_order_blank=hint.needs_order_blank_attention,
            catalog_empty=hint.catalog_empty,
            needs_monthly_upload=hint.needs_monthly_upload,
            last_order_blank_applied_at=hint.last_success_applied_at,
        ),
        items=[AggRow.from_agg(row) for row in rows],
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

    async with orchestrator.catalog_safe_overview_context():
        freshness = await orchestrator.ensure_overview_fresh(background_tasks)
    stale = any(info.stale for info in freshness)

    hint = await compute_order_blank_reminder_state(session)

    query = select(AggStoreProduct).options(joinedload(AggStoreProduct.product)).where(
        AggStoreProduct.article == article
    )
    total = await session.scalar(
        select(func.count()).select_from(query.order_by(None).subquery())
    ) or 0
    rows = (
        await session.execute(
            query.order_by(AggStoreProduct.store_id).limit(limit).offset(offset)
        )
    ).scalars().all()

    warn = _overview_warning_meta(
        stale=stale,
        catalog_empty=hint.catalog_empty,
        needs_monthly_upload=hint.needs_monthly_upload,
    )

    return OverviewResponse(
        meta=OverviewMeta(
            total=int(total),
            limit=limit,
            offset=offset,
            stale=stale,
            warning=warn,
            needs_order_blank=hint.needs_order_blank_attention,
            catalog_empty=hint.catalog_empty,
            needs_monthly_upload=hint.needs_monthly_upload,
            last_order_blank_applied_at=hint.last_success_applied_at,
        ),
        items=[AggRow.from_agg(row) for row in rows],
    )


def _entity(name: str):
    from src.backend.app.models import SyncEntity

    return SyncEntity(name)
