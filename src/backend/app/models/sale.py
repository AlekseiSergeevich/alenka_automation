from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.db.base import Base


class SaleLine(Base):
    __tablename__ = "sale_line"
    __table_args__ = (
        Index("ix_sale_line_store_sold_at", "store_id", "sold_at"),
        Index("ix_sale_line_article_sold_at", "article", "sold_at"),
        Index(
            "ix_sale_line_sold_at_brin",
            "sold_at",
            postgresql_using="brin",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("store.id", ondelete="CASCADE"), nullable=False
    )
    article: Mapped[str] = mapped_column(
        String(128), ForeignKey("product.article", ondelete="CASCADE"), nullable=False
    )
    sold_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    # Optional identifier from Saby order payload. When present we can move to
    # (external_order_id, line_no) idempotency, otherwise we rely on the
    # DELETE-window + INSERT strategy handled in the ingestion service.
    external_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    line_no: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
