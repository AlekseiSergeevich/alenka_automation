"""order_blank_upload — метаданные загрузок бланка заказа

Revision ID: 0005_obu
Revises: 0004_sync_ps
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_obu"
down_revision: str | Sequence[str] | None = "0004_sync_ps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "order_blank_upload",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("stored_path", sa.String(length=1024), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_order_blank_upload_applied_at",
        "order_blank_upload",
        ["applied_at"],
        unique=False,
    )
    op.create_index(
        "ix_order_blank_upload_status_applied",
        "order_blank_upload",
        ["status", "applied_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_order_blank_upload_status_applied", table_name="order_blank_upload")
    op.drop_index("ix_order_blank_upload_applied_at", table_name="order_blank_upload")
    op.drop_table("order_blank_upload")
