"""initial schema: store, product, stock_current, sale_line, sync_run, agg_store_product

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-19 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "store",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("address", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("locality", sa.String(length=256), nullable=False, server_default=""),
        sa.Column(
            "prices",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{}'::int[]"),
        ),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "product",
        sa.Column("article", sa.String(length=128), primary_key=True),
        sa.Column("name", sa.String(length=1024), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "stock_current",
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
        sa.Column("balance", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "sale_line",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "store_id",
            sa.BigInteger(),
            sa.ForeignKey("store.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "article",
            sa.String(length=128),
            sa.ForeignKey("product.article", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("qty", sa.Numeric(18, 3), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("external_order_id", sa.String(length=128), nullable=True),
        sa.Column("line_no", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_sale_line_store_sold_at", "sale_line", ["store_id", "sold_at"], unique=False
    )
    op.create_index(
        "ix_sale_line_article_sold_at", "sale_line", ["article", "sold_at"], unique=False
    )
    op.create_index(
        "ix_sale_line_sold_at_brin",
        "sale_line",
        ["sold_at"],
        unique=False,
        postgresql_using="brin",
    )

    sync_entity = postgresql.ENUM("points", "stock", "sales", name="sync_entity")
    sync_status = postgresql.ENUM("running", "success", "failed", name="sync_status")
    sync_entity.create(op.get_bind(), checkfirst=True)
    sync_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "sync_run",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "entity",
            postgresql.ENUM("points", "stock", "sales", name="sync_entity", create_type=False),
            nullable=False,
        ),
        sa.Column("store_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("running", "success", "failed", name="sync_status", create_type=False),
            nullable=False,
            server_default="running",
        ),
        sa.Column("cursor_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_upserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_sync_run_entity", "sync_run", ["entity"], unique=False)
    op.create_index("ix_sync_run_store_id", "sync_run", ["store_id"], unique=False)

    op.create_table(
        "agg_store_product",
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
        sa.Column("store_name", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("product_name", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("unit", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("stock_balance", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("stock_captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sales_qty_30d", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("sales_qty_90d", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("sales_qty_window", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("avg_daily_qty", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("last_sale_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("days_of_cover", sa.Numeric(18, 3), nullable=True),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_agg_store_product_store", "agg_store_product", ["store_id"], unique=False
    )
    op.create_index(
        "ix_agg_store_product_article", "agg_store_product", ["article"], unique=False
    )
    op.create_index(
        "ix_agg_store_product_days_of_cover",
        "agg_store_product",
        ["days_of_cover"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agg_store_product_days_of_cover", table_name="agg_store_product")
    op.drop_index("ix_agg_store_product_article", table_name="agg_store_product")
    op.drop_index("ix_agg_store_product_store", table_name="agg_store_product")
    op.drop_table("agg_store_product")

    op.drop_index("ix_sync_run_store_id", table_name="sync_run")
    op.drop_index("ix_sync_run_entity", table_name="sync_run")
    op.drop_table("sync_run")

    postgresql.ENUM(name="sync_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="sync_entity").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_sale_line_sold_at_brin", table_name="sale_line")
    op.drop_index("ix_sale_line_article_sold_at", table_name="sale_line")
    op.drop_index("ix_sale_line_store_sold_at", table_name="sale_line")
    op.drop_table("sale_line")

    op.drop_table("stock_current")
    op.drop_table("product")
    op.drop_table("store")
