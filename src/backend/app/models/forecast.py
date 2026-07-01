from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.db.base import Base


class Forecast(Base):
    __tablename__ = "forecast"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    month: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    predicted_qty: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
