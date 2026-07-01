from __future__ import annotations

from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from src.backend.app.db.base import Base


class OrderBlankItem(Base):
    """Строки, распарсенные из файла бланка заказа (.xls).
    Содержат все статические признаки, необходимые для ML-модели.
    """

    __tablename__ = "order_blank_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    upload_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("order_blank_upload.id", ondelete="CASCADE"), nullable=False
    )

    # Идентификаторы
    sku: Mapped[str] = mapped_column(String(128), nullable=False, index=True)  # УКП
    name: Mapped[str] = mapped_column(String(1024), nullable=False)  # Название SKU

    # Бизнес-признаки и фичи для ML
    is_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # Из колонки "Признаки" == "Новинка"
    focus: Mapped[str] = mapped_column(String(64), nullable=False, default="Прочее")
    abc_group: Mapped[str] = mapped_column(String(64), nullable=False, default="Unknown")
    item_type: Mapped[str] = mapped_column(String(128), nullable=False, default="Unknown")  # Тип
    brand: Mapped[str] = mapped_column(String(128), nullable=False, default="Unknown")  # Бренд

    # Числовые признаки
    base_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)  # Базовая цена за короб
    shelf_life_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # Срок годности, дн.
    weight_gr: Mapped[Decimal] = mapped_column(Numeric(18, 3), nullable=False, default=0)  # Фасовка - вес штуки, гр
