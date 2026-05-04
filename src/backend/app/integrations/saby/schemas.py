from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SabyConnectionStatus(BaseModel):
    configured: bool
    auth_url: str
    api_base_url: str
    service_url: str
    has_access_token: bool


# --- Точка продаж ---


class PointSchema(BaseModel):
    address: str = Field(default="", alias="address", description="Адрес точки продаж")
    id: int = Field(alias="id", description="Идентификатор точки продаж")
    locality: str = Field(default="", alias="locality", description="Населенный пункт")
    name: str = Field(default="", alias="name", description="Название точки продаж")
    prices: list[int] = Field(
        default_factory=list, description="Список идентификаторов прайс-листов"
    )

    model_config = ConfigDict(extra="ignore")


class SalesPointsResponse(BaseModel):
    salesPoints: list[PointSchema] = Field(
        default_factory=list,
        alias="salesPoints",
        description="Список точек продаж",
    )

    model_config = ConfigDict(extra="ignore")


# --- Склад (JSON-RPC) ---


class WarehouseSchema(BaseModel):
    id: str = Field(alias="id", description="Идентификатор склада (строка из Saby)")
    address: str = Field(alias="address", default="", description="Адрес склада")
    name: str = Field(alias="name", default="", description="Название склада")

    model_config = ConfigDict(extra="ignore")

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, UUID):
            return str(v)
        return str(v)


class WarehousesResponse(BaseModel):
    hasMore: bool = Field(default=False, alias="hasMore", description="Есть ли еще данные")
    warehouses: list[WarehouseSchema] = Field(
        default_factory=list,
        alias="warehouses",
        description="Список складов",
    )

    model_config = ConfigDict(extra="ignore")


# --- Прайс-лист ---


class OutComeSchema(BaseModel):
    hasMore: bool = Field(default=False, alias="hasMore", description="Есть ли еще данные")

    model_config = ConfigDict(extra="ignore")


class PriceListSchema(BaseModel):
    id: int = Field(alias="id", description="Идентификатор прайс-листа")
    name: str = Field(alias="name", default="", description="Название прайс-листа")
    outCome: OutComeSchema = Field(
        default_factory=OutComeSchema,
        alias="outCome",
        description="Признак наличия записей на следующей странице",
    )

    model_config = ConfigDict(extra="ignore")


# --- Номенклатура / остаток по точке (retail v2 list) ---


class ProductBalanceSchema(BaseModel):
    article: str = ""
    balance: str = ""
    name: str = ""
    unit: str = ""

    model_config = ConfigDict(extra="ignore")


class NomenclatureListResponse(BaseModel):
    """Ответ GET /retail/v2/nomenclature/list — список позиций в разных ключах."""

    nomenclatures: list[dict[str, Any]] = Field(default_factory=list, alias="nomenclatures")
    items: list[dict[str, Any]] = Field(default_factory=list, alias="items")
    # Имя поля не `list`: на Python 3.14 pydantic воспринимает аннотацию как Field().
    legacy_list_rows: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="list",
        description='Ключ ответа Saby ``"list"``.',
    )
    result: list[dict[str, Any]] = Field(default_factory=list, alias="result")
    results: list[dict[str, Any]] = Field(default_factory=list, alias="results")
    data: list[dict[str, Any]] = Field(default_factory=list, alias="data")
    rows: list[dict[str, Any]] = Field(default_factory=list, alias="rows")

    model_config = ConfigDict(extra="ignore")


class ProductSchema(BaseModel):
    article: str
    name: str
    count: float
    unit: str

    model_config = ConfigDict(extra="ignore")


# --- Заказы / продажи (retail order list) ---


class OrderLinePayload(BaseModel):
    """Строка заказа в ответе Saby (поля могут отличаться по версии API)."""

    article: str | None = None
    name: str | None = ""
    unit: str | None = ""
    count: Any = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("article", mode="before")
    @classmethod
    def _coerce_article(cls, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)


class RetailOrderPayload(BaseModel):
    """Один заказ из /retail/order/list."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: int | str | None = None
    orderId: int | str | None = Field(default=None, alias="orderId")
    uuid: str | None = None

    nomenclatures: list[dict[str, Any]] | None = None
    items: list[dict[str, Any]] | None = None
    positions: list[dict[str, Any]] | None = None
    lines: list[dict[str, Any]] | None = None
    products: list[dict[str, Any]] | None = None

    dateTime: str | datetime | None = None
    date_time: str | datetime | None = None
    date_time_iso: str | datetime | None = Field(
        default=None,
        alias="datetime",
        description='Альтернативное поле времени (ключ "datetime").',
    )
    date: str | datetime | None = None
    createdAt: str | datetime | None = None
    created_at: str | datetime | None = None

    def order_lines_raw(self) -> list[dict[str, Any]]:
        for key in ("nomenclatures", "items", "positions", "lines", "products"):
            v = getattr(self, key, None)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        return []


class OrderListResponse(BaseModel):
    """Обёртка для пагинированного списка заказов."""

    orders: list[dict[str, Any]] = Field(default_factory=list, alias="orders")
    items: list[dict[str, Any]] = Field(default_factory=list, alias="items")
    legacy_list_orders: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="list",
        description='Ключ ответа ``"list"``.',
    )
    result: list[dict[str, Any]] = Field(default_factory=list, alias="result")
    results: list[dict[str, Any]] = Field(default_factory=list, alias="results")
    data: list[dict[str, Any]] = Field(default_factory=list, alias="data")
    rows: list[dict[str, Any]] = Field(default_factory=list, alias="rows")

    model_config = ConfigDict(extra="ignore")


# --- Payload helpers (устойчивее, чем «первый list в values») ---


def iter_sales_point_dicts(payload: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    sp = payload.get("salesPoints")
    if isinstance(sp, list):
        return [x for x in sp if isinstance(x, dict)]
    for key in (
        "items",
        "list",
        "result",
        "results",
        "payload",
        "data",
        "rows",
        "points",
    ):
        v = payload.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    return []


def iter_nomenclature_dicts(payload: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    try:
        parsed = NomenclatureListResponse.model_validate(payload)
        for bucket in (
            parsed.nomenclatures,
            parsed.items,
            parsed.legacy_list_rows,
            parsed.result,
            parsed.results,
            parsed.data,
            parsed.rows,
        ):
            if bucket:
                return [x for x in bucket if isinstance(x, dict)]
    except Exception:
        pass
    for key in (
        "nomenclatures",
        "items",
        "list",
        "result",
        "results",
        "payload",
        "data",
        "rows",
    ):
        v = payload.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    for value in payload.values():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return [x for x in value if isinstance(x, dict)]
    return []


def iter_order_dicts(payload: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    try:
        parsed = OrderListResponse.model_validate(payload)
        for bucket in (
            parsed.orders,
            parsed.items,
            parsed.legacy_list_orders,
            parsed.result,
            parsed.results,
            parsed.data,
            parsed.rows,
        ):
            if bucket:
                return [x for x in bucket if isinstance(x, dict)]
    except Exception:
        pass
    for key in ("orders", "items", "list", "result", "results", "payload", "data", "rows"):
        v = payload.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    for value in payload.values():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return [x for x in value if isinstance(x, dict)]
    return []
