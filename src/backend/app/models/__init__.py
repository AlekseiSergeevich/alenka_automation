"""ORM models aggregated for Alembic autodiscovery."""

from src.backend.app.models.aggregate import AggStoreProduct
from src.backend.app.models.forecast import Forecast
from src.backend.app.models.order_blank_upload import OrderBlankUpload
from src.backend.app.models.order_blank_item import OrderBlankItem
from src.backend.app.models.product import Product
from src.backend.app.models.sale import SaleLine
from src.backend.app.models.sales_monthly import SalesMonthly
from src.backend.app.models.stock import StockCurrent
from src.backend.app.models.store import Store
from src.backend.app.models.sync import SyncEntity, SyncRun, SyncStatus

__all__ = [
    "AggStoreProduct",
    "Forecast",
    "OrderBlankUpload",
    "OrderBlankItem",
    "Product",
    "SaleLine",
    "SalesMonthly",
    "StockCurrent",
    "Store",
    "SyncEntity",
    "SyncRun",
    "SyncStatus",
]
