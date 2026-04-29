from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.db.base import Base


class StockCurrent(Base):
    __tablename__ = "stock_current"

    store_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("store.id", ondelete="CASCADE"), primary_key=True
    )
    article: Mapped[str] = mapped_column(
        String(128), ForeignKey("product.article", ondelete="CASCADE"), primary_key=True
    )
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
