from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class SabyConnectionStatus(BaseModel):
    configured: bool
    auth_url: str
    api_base_url: str
    service_url: str
    has_access_token: bool


# Точка продаж
class PointSchema(BaseModel):
    address: str = Field(alias="address", description="Адрес точки продаж")
    id: int = Field(alias="id", description="Идентификатор точки продаж")
    locality: str = Field(alias="locality", description="Населенный пункт")
    name: str = Field(alias="name", description="Название точки продаж")
    prices: list[int] = Field(description="Список идентификаторов прайс-листов")

    model_config = ConfigDict(extra="ignore")


class SalesPointsResponse(BaseModel):
    salesPoints: list[PointSchema] = Field(
        alias="salesPoints", description="Список точек продаж"
    )


    model_config = ConfigDict(extra="ignore")

# Склад
class WarehouseSchema(BaseModel):
    id: UUID = Field(alias="id", description="Идентификатор склада")
    address: str = Field(alias="address", description="Адрес склада")
    name: str = Field(alias="name", description="Название склада")

    model_config = ConfigDict(extra="ignore")


class WarehousesResponse(BaseModel):
    hasMore: bool = Field(alias="hasMore", description="Есть ли еще данные")
    warehouses: list[WarehouseSchema] = Field(
        alias="warehouses", description="Список складов"
    )

    model_config = ConfigDict(extra="ignore")


# Прайс-лист
class OutComeSchema(BaseModel):
    hasMore: bool = Field(alias="hasMore", description="Есть ли еще данные")

    model_config = ConfigDict(extra="ignore")


class PriceListSchema(BaseModel):
    id: int = Field(alias="id", description="Идентификатор прайс-листа")
    name: str = Field(alias="name", description="Название прайс-листа")
    outCome: OutComeSchema = Field(
        alias="outCome", description="Признак наличия записей на следующей странице"
    )

    model_config = ConfigDict(extra="ignore")


class ProductBalanceScema(BaseModel):
    article: str
    balance: str
    name: str
    unit: str

    model_config = ConfigDict(extra="ignore")


class ProductSchema(BaseModel):
    article: str
    name: str
    count: float
    unit: str

    model_config = ConfigDict(extra="ignore")
