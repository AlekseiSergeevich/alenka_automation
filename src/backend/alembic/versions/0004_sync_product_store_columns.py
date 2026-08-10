"""product — type/focus/group_abc/feature/quantity_in_box; store — warehouse_id replaces prices

Revision ID: 0004_sync_ps
Revises: 0003_nom
Create Date: 2026-05-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_sync_ps"
down_revision: str | Sequence[str] | None = "0003_nom"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product",
        sa.Column("type", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "product",
        sa.Column("focus", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "product",
        sa.Column("group_abc", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "product",
        sa.Column("feature", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "product",
        sa.Column("quantity_in_box", sa.Numeric(18, 3), nullable=False, server_default="0"),
    )

    op.add_column(
        "store",
        sa.Column("warehouse_id", sa.Integer(), nullable=False, server_default="0"),
    )
    op.drop_column("store", "prices")


def downgrade() -> None:
    op.add_column(
        "store",
        sa.Column(
            "prices",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{}'::int[]"),
        ),
    )
    op.drop_column("store", "warehouse_id")

    op.drop_column("product", "quantity_in_box")
    op.drop_column("product", "feature")
    op.drop_column("product", "group_abc")
    op.drop_column("product", "focus")
    op.drop_column("product", "type")
