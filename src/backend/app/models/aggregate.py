from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.backend.app.models.product import Product

from src.backend.app.db.base import Base


class AggStoreProduct(Base):
    """User-facing denormalized view per (store, product).

    Refreshed from `sales_monthly`, `stock_current` и `sale_line` после ingestion.
    """

    __tablename__ = "agg_store_product"
    __table_args__ = (
        Index("ix_agg_store_product_store", "store_id"),
        Index("ix_agg_store_product_article", "article"),
        Index("ix_agg_store_product_days_of_cover", "days_of_cover"),
        Index("ix_agg_store_product_sales_qty_3m", "sales_qty_3m"),
    )

    store_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("store.id", ondelete="CASCADE"), primary_key=True
    )
    article: Mapped[str] = mapped_column(
        String(128), ForeignKey("product.article", ondelete="CASCADE"), primary_key=True
    )

    store_name: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    product_name: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    unit: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    product: Mapped["Product"] = relationship(
        "Product",
        primaryjoin="AggStoreProduct.article == Product.article",
        foreign_keys="[AggStoreProduct.article]",
        uselist=False,
    )

    stock_balance: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    stock_captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    monthly_sales: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    sales_qty_3m: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    avg_daily_qty: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    last_sale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    days_of_cover: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)

    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
