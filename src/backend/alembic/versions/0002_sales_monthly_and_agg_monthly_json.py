"""sales_monthly table; agg_store_product rolling sales -> monthly JSON + qty_3m

Revision ID: 0002_sales_monthly_agg
Revises: 0001_initial
Create Date: 2026-05-04

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_sales_monthly_agg"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sales_monthly",
        sa.Column(
            "store_id",
            sa.BigInteger(),
            sa.ForeignKey("store.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "article",
            sa.String(length=128),
            sa.ForeignKey("product.article", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("month_start", sa.Date(), nullable=False, primary_key=True),
        sa.Column("qty", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("orders_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_sales_monthly_store_month",
        "sales_monthly",
        ["store_id", "month_start"],
        unique=False,
    )
    op.create_index(
        "ix_sales_monthly_article_month",
        "sales_monthly",
        ["article", "month_start"],
        unique=False,
    )

    op.add_column(
        "agg_store_product",
        sa.Column(
            "monthly_sales",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "agg_store_product",
        sa.Column(
            "sales_qty_3m",
            sa.Numeric(18, 3),
            nullable=False,
            server_default="0",
        ),
    )
    op.drop_index("ix_agg_store_product_days_of_cover", table_name="agg_store_product")
    op.drop_column("agg_store_product", "sales_qty_30d")
    op.drop_column("agg_store_product", "sales_qty_90d")
    op.drop_column("agg_store_product", "sales_qty_window")
    op.create_index(
        "ix_agg_store_product_days_of_cover",
        "agg_store_product",
        ["days_of_cover"],
        unique=False,
    )
    op.create_index(
        "ix_agg_store_product_sales_qty_3m",
        "agg_store_product",
        ["sales_qty_3m"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agg_store_product_sales_qty_3m", table_name="agg_store_product")
    op.drop_index("ix_agg_store_product_days_of_cover", table_name="agg_store_product")
    op.drop_column("agg_store_product", "sales_qty_3m")
    op.drop_column("agg_store_product", "monthly_sales")
    op.add_column(
        "agg_store_product",
        sa.Column("sales_qty_window", sa.Numeric(18, 3), nullable=False, server_default="0"),
    )
    op.add_column(
        "agg_store_product",
        sa.Column("sales_qty_90d", sa.Numeric(18, 3), nullable=False, server_default="0"),
    )
    op.add_column(
        "agg_store_product",
        sa.Column("sales_qty_30d", sa.Numeric(18, 3), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_agg_store_product_days_of_cover",
        "agg_store_product",
        ["days_of_cover"],
        unique=False,
    )

    op.drop_index("ix_sales_monthly_article_month", table_name="sales_monthly")
    op.drop_index("ix_sales_monthly_store_month", table_name="sales_monthly")
    op.drop_table("sales_monthly")
