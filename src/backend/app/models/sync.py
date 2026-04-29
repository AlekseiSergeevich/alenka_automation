import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.db.base import Base


class SyncEntity(str, enum.Enum):
    points = "points"
    stock = "stock"
    sales = "sales"


class SyncStatus(str, enum.Enum):
    running = "running"
    success = "success"
    failed = "failed"


class SyncRun(Base):
    __tablename__ = "sync_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity: Mapped[SyncEntity] = mapped_column(
        Enum(SyncEntity, name="sync_entity"), nullable=False, index=True
    )
    # Nullable: points sync is global, stock/sales can be either global or per store.
    store_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[SyncStatus] = mapped_column(
        Enum(SyncStatus, name="sync_status"),
        nullable=False,
        default=SyncStatus.running,
    )

    cursor_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cursor_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_upserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
