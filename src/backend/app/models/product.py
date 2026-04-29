from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.db.base import Base


class Product(Base):
    __tablename__ = "product"

    # `article` is the only cross-cutting natural key exposed by Saby
    # (appears in nomenclature, balances and order lines).
    article: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(1024), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
