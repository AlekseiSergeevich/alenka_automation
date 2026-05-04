from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from src.backend.app.api.deps import get_saby_client, require_admin
from src.backend.app.core.config import Settings, get_settings
from src.backend.app.integrations.saby.client import SabyClient
from src.backend.app.integrations.saby.schemas import (
    NomenclatureListResponse,
    SalesPointsResponse,
    SabyConnectionStatus,
)


router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/status", response_model=SabyConnectionStatus)
async def saby_connection_status(
    settings: Settings = Depends(get_settings),
) -> SabyConnectionStatus:
    return SabyConnectionStatus(
        configured=settings.saby_is_configured,
        auth_url=settings.saby_auth_url,
        api_base_url=settings.saby_api_base_url,
        service_url=settings.saby_service_url,
        has_access_token=bool(settings.saby_access_token),
    )


@router.get("/sales-points", response_model=SalesPointsResponse)
async def list_sales_points(
    product: str = Query(default="retail", description="Saby product: retail or delivery."),
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=100, ge=1, le=500),
    client: SabyClient = Depends(get_saby_client),
) -> SalesPointsResponse:
    payload = await client.list_sales_points(product=product, page=page, page_size=page_size)
    return SalesPointsResponse.model_validate(payload)


@router.get(
    "/products",
    summary="Список номенклатуры (каталог)",
    description=(
        "Прокси к GET `/retail/v2/nomenclature/list`. "
        "Товары из прайса при указании priceListId; из каталога — если priceListId не передан. "
        "Документация: "
        "https://saby.ru/help/integration/api/app_sale/sale_delyvery/catalog"
    ),
)
@router.get(
    "/catalog",
    summary="Список номенклатуры (каталог)",
    description=(
        "То же, что `/products`. См. "
        "https://saby.ru/help/integration/api/app_sale/sale_delyvery/catalog"
    ),
)
async def list_products(
    point_id: int | None = Query(
        default=None,
        description="Точка продаж (pointId в API Saby); нужна, если передан price_list_id.",
    ),
    price_list_id: int | None = Query(
        default=None,
        description="Идентификатор прайса или колонки цен (из «Получить прайс-лист»).",
    ),
    no_stop_list: bool | None = Query(
        default=None,
        alias="noStopList",
        description="Исключить позиции из стоп-листа.",
    ),
    search_string: str | None = Query(
        default=None,
        alias="searchString",
        description="Поиск по названию или части названия.",
    ),
    with_balance: bool = Query(
        default=True,
        description="Передавать остаток по складу точки (balance); в Saby — withBalance.",
    ),
    with_barcode: bool | None = Query(
        default=None,
        alias="withBarcode",
        description="Передавать штрихкоды в ответе.",
    ),
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=100, ge=1, le=1000),
    position: int | None = Query(
        default=None,
        description="Курсор последней записи с предыдущей страницы (курсовая навигация).",
    ),
    order: Literal["before", "after"] | None = Query(
        default=None,
        description="Для курсовой навигации вместе с position: before или after.",
    ),
    client: SabyClient = Depends(get_saby_client),
) -> NomenclatureListResponse:
    payload = await client.list_products(
        point_id=point_id,
        price_list_id=price_list_id,
        no_stop_list=no_stop_list,
        search_string=search_string,
        with_balance=with_balance,
        with_barcode=with_barcode,
        page=page,
        page_size=page_size,
        position=position,
        order=order,
    )
    return NomenclatureListResponse.model_validate(payload)


@router.get("/balances")
async def list_balances(
    company_id: list[int] = Query(..., alias="companyId"),
    warehouse_id: list[int] = Query(..., alias="warehouseId"),
    nomenclature_id: list[int] | None = Query(default=None, alias="nomenclatureId"),
    price_list_id: list[int] | None = Query(default=None, alias="priceListId"),
    client: SabyClient = Depends(get_saby_client),
) -> dict[str, Any]:
    return await client.list_balances(
        company_ids=company_id,
        warehouse_ids=warehouse_id,
        nomenclature_ids=nomenclature_id,
        price_list_ids=price_list_id,
    )


@router.get("/sales")
async def list_sales(
    from_datetime: datetime = Query(..., alias="fromDateTime"),
    to_datetime: datetime | None = Query(default=None, alias="toDateTime"),
    point_id: int = Query(..., alias="pointId"),
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=100, ge=1, le=500),
    client: SabyClient = Depends(get_saby_client),
) -> dict[str, Any]:
    return await client.list_sales(
        from_datetime=from_datetime,
        to_datetime=to_datetime,
        point_id=point_id,
        page=page,
        page_size=page_size,
    )


@router.get("/price-list")
async def list_price_list(
    pointId: int = Query(default=0, alias="pointId"),
    actualDate: date | None = Query(default=None, alias="actualDate"),
    page: int = Query(default=0, ge=0),
    pageSize: int = Query(default=100, ge=1, le=1000),
    client: SabyClient = Depends(get_saby_client),
) -> dict[str, Any]:
    ad = actualDate or date.today()
    actual_dt = datetime(ad.year, ad.month, ad.day, tzinfo=timezone.utc)
    return await client.price_list(
        pointId=pointId, actualDate=actual_dt, page=page, pageSize=pageSize
    )


@router.get("/warehouses")
async def list_warehouses(
    page: int = Query(default=0, ge=0, description="Номер страницы (в filter для sabyWarehouse.List)."),
    limit: int = Query(default=100, ge=1, le=1000, description="Размер страницы (в filter)."),
    client: SabyClient = Depends(get_saby_client),
) -> dict[str, Any]:
    return await client.list_warehouses(page=page, limit=limit)
