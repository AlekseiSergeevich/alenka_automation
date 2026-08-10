from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.db.base import Base


class SalesMonthly(Base):
    """Помесячные продажи по точке и артикулу (агрегат из sale_line)."""

    __tablename__ = "sales_monthly"
    __table_args__ = (
        Index("ix_sales_monthly_store_month", "store_id", "month_start"),
        Index("ix_sales_monthly_article_month", "article", "month_start"),
    )

    store_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("store.id", ondelete="CASCADE"), primary_key=True
    )
    article: Mapped[str] = mapped_column(
        String(128), ForeignKey("product.article", ondelete="CASCADE"), primary_key=True
    )
    month_start: Mapped[date] = mapped_column(Date, primary_key=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    unit: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
