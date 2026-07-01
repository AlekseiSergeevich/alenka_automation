from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.db.base import Base


class OrderBlankUpload(Base):
    """Метаданные загрузки файла бланка заказа (.xls)."""

    __tablename__ = "order_blank_upload"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    #: Путь относительно каталога ``order_blank_storage_dir``.
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
