from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, AliasChoices, ConfigDict, Field, field_validator, model_validator


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
    warehouse_id: int = Field(
        default=0,
        validation_alias=AliasChoices("warehouseId", "warehouse_id", "WarehouseId"),
        description="Склад по умолчанию для точки (если отдаёт API); иначе 0",
    )

    model_config = ConfigDict(extra="ignore")

    @field_validator("warehouse_id", mode="before")
    @classmethod
    def _coerce_warehouse_id(cls, v: Any) -> int:
        if v is None or v == "":
            return 0
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, int):
            return v
        try:
            return int(str(v).strip())
        except ValueError:
            return 0


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


class PriceListListResponse(BaseModel):
    """Ответ GET /retail/nomenclature/price-list — список прайсов в разных ключах."""

    price_lists: list[dict[str, Any]] = Field(
        default_factory=list,
        validation_alias=AliasChoices("priceLists", "price_lists", "PriceLists"),
    )
    items: list[dict[str, Any]] = Field(default_factory=list, alias="items")
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


def iter_price_list_dicts(payload: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    """Нормализует ответ price-list к списку dict с полем ``id``."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    try:
        parsed = PriceListListResponse.model_validate(payload)
        for bucket in (
            parsed.price_lists,
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
        "priceLists",
        "price_lists",
        "PriceLists",
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


def first_price_list_id(payload: dict[str, Any] | list[Any] | None) -> int | None:
    """Первый валидный ``id`` из ответа price-list (как договорено — обычно один прайс на точку)."""
    for d in iter_price_list_dicts(payload):
        raw = d.get("id")
        if raw is None:
            raw = d.get("Id")
        if raw is None:
            continue
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            continue
    return None


# --- Номенклатура / остаток по точке (retail v2 list) ---


class ProductBalanceSchema(BaseModel):
    """Номенклатура склада точки из Retail v2."""

    #: Артикул из карточки (если заполнен в Saby / 1С); иначе — fallback ниже.
    article: str = ""
    #: Внутренний ``nomNumber`` Saby (`X4924446`), совпадает с ``NomenclatureNumber`` в чеках.
    nom_number: str = ""
    balance: str = ""
    name: str = ""
    unit: str = ""
    type: str = ""
    focus: str = ""
    group_abc: str = ""
    feature: str = ""
    quantity_in_box: Decimal = Field(default=Decimal("0"))

    model_config = ConfigDict(extra="ignore")

    @field_validator("quantity_in_box", mode="before")
    @classmethod
    def _coerce_quantity_in_box(cls, v: Any) -> Decimal:
        if v is None or v == "":
            return Decimal("0")
        if isinstance(v, Decimal):
            return v
        try:
            return Decimal(str(v).strip().replace(",", "."))
        except Exception:
            return Decimal("0")

    @staticmethod
    def _first_str(d: dict[str, Any], keys: tuple[str, ...]) -> str:
        for k in keys:
            raw = d.get(k)
            if raw is None:
                continue
            s = str(raw).strip()
            if s:
                return s
        return ""

    @model_validator(mode="before")
    @classmethod
    def _fallback_article_balance(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        nn = ""
        for k in ("nomNumber", "NomenclatureNumber", "nomenclatureNumber"):
            raw = d.get(k)
            if raw is None:
                continue
            s = str(raw).strip()
            if s:
                nn = s
                break
        d["nom_number"] = nn

        art = d.get("article")
        if art is None or str(art).strip() == "":
            for k in ("nomNumber", "NomenclatureNumber", "nomenclatureNumber", "short_code"):
                raw = d.get(k)
                if raw is None:
                    continue
                s = str(raw).strip()
                if s:
                    d["article"] = s
                    break

        bal = d.get("balance")
        if bal is None:
            d["balance"] = ""
        elif not isinstance(bal, str):
            d["balance"] = str(bal)

        if d.get("article") is None:
            d["article"] = ""
        if d.get("nom_number") is None:
            d["nom_number"] = ""
        if d.get("name") is None:
            d["name"] = ""
        if d.get("unit") is None:
            d["unit"] = ""

        d["type"] = cls._first_str(
            d,
            ("type", "Type", "productType", "ProductType", "nomenclatureType", "NomenclatureType"),
        )
        d["focus"] = cls._first_str(d, ("focus", "Focus", "productFocus", "marketingFocus"))
        d["group_abc"] = cls._first_str(
            d,
            ("groupAbc", "group_abc", "abcGroup", "ABC", "ABCGroup", "segmentAbc"),
        )
        d["feature"] = cls._first_str(d, ("feature", "Feature", "productFeature", "label"))
        qraw = None
        for k in (
            "quantityInBox",
            "quantity_in_box",
            "itemsPerBox",
            "ItemsPerBox",
            "multiplicity",
            "Multiplicity",
            "inBox",
            "InBox",
        ):
            if d.get(k) is not None and str(d.get(k)).strip() != "":
                qraw = d.get(k)
                break
        d["quantity_in_box"] = qraw if qraw is not None else d.get("quantity_in_box")
        return d


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
    is_return: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("isReturn", "IsReturn", "is_return", "IsReturned", "isReturned"),
        description="Флаг возврата",
    )

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def _coerce_sale_line_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if not d.get("article") and not d.get("Article"):
            for k in (
                "NomenclatureNumber",
                "nomenclatureNumber",
                "nomNumber",
                "NomNumber",
            ):
                raw = d.get(k)
                if raw is None:
                    continue
                s = str(raw).strip()
                if s:
                    d["article"] = s
                    break
        if d.get("name") in (None, "") and d.get("Name") is not None:
            d["name"] = d.get("Name")
        if not d.get("unit") and (d.get("UnitName") is not None or d.get("Unit") is not None):
            u = d.get("UnitName") if d.get("UnitName") is not None else d.get("Unit")
            if u is not None:
                d["unit"] = str(u)
        if d.get("count") is None and d.get("Count") is None:
            q = d.get("Quantity")
            if q is not None:
                d["count"] = q
        return d

    @field_validator("article", mode="before")
    @classmethod
    def _coerce_article(cls, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)


class RetailOrderPayload(BaseModel):
    """Один заказ из /retail/order/list."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    sale_nomenclatures: list[dict[str, Any]] | None = Field(
        default=None,
        validation_alias=AliasChoices("SaleNomenclatures", "saleNomenclatures"),
        description="Позиции чека из ответа Saby Retail (частый формат заказов).",
    )

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
        if isinstance(self.sale_nomenclatures, list):
            rows = [x for x in self.sale_nomenclatures if isinstance(x, dict)]
            if rows:
                return rows
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
