from datetime import datetime
from typing import Any

from sqlalchemy import ARRAY, BigInteger, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.db.base import Base


class Store(Base):
    __tablename__ = "store"

    # Id equals Saby PointSchema.id, kept as the primary key across the system.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    address: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    locality: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    warehouse_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Первый id из GET /retail/nomenclature/price-list для точки (кэш для list_products).
    price_list_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
