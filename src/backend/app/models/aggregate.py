from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.db.base import Base


class AggStoreProduct(Base):
    """User-facing denormalized view per (store, product).

    Refreshed from `sale_line` + `stock_current` after each ingestion run.
    """

    __tablename__ = "agg_store_product"
    __table_args__ = (
        Index("ix_agg_store_product_store", "store_id"),
        Index("ix_agg_store_product_article", "article"),
        Index("ix_agg_store_product_days_of_cover", "days_of_cover"),
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

    stock_balance: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    stock_captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sales_qty_30d: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    sales_qty_90d: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    sales_qty_window: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    avg_daily_qty: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    last_sale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    days_of_cover: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)

    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
