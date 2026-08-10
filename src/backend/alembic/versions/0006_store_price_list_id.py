"""store — кэш price_list_id для Saby /retail/v2/nomenclature/list

Revision ID: 0006_plid
Revises: 0005_obu
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_plid"
down_revision: str | Sequence[str] | None = "0005_obu"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "store",
        sa.Column("price_list_id", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("store", "price_list_id")
