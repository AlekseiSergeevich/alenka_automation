"""product.nom_number — внутренний номер Saby (nomNumber) для связи с SaleNomenclatures

Revision ID: 0003_nom
Revises: 0002_sales_monthly_agg
Create Date: 2026-05-07

Уникальный индекс намеренно не ставим: при прошлых ошибочных ключах могли быть
дубликаты (article как X‑код vs «боевой» артикул); разрешение делается в коде ingestion.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_nom"
down_revision: str | Sequence[str] | None = "0002_sales_monthly_agg"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product",
        sa.Column(
            "nom_number",
            sa.String(length=128),
            nullable=True,
        ),
    )
    op.create_index("ix_product_nom_number", "product", ["nom_number"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_product_nom_number", table_name="product")
    op.drop_column("product", "nom_number")
