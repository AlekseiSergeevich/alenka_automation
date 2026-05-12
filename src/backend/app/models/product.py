from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.db.base import Base


class Product(Base):
    __tablename__ = "product"

    #: ``article`` из номенклатуры Retail / 1С; ``nom_number`` — внутренний nomNumber /
    #: NomenclatureNumber вида ``X4924446``, чтобы сопоставлять строки чеков.
    article: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(1024), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    focus: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    group_abc: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    feature: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    quantity_in_box: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)
    nom_number: Mapped[str | None] = mapped_column(String(128), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
