"""init tables

Revision ID: 0001_init_tables
Revises: 
Create Date: 2026-04-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0001_init_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "exchange_rates" not in tables:
        op.create_table(
            "exchange_rates",
            sa.Column("date", sa.String(), nullable=False),
            sa.Column("char_code", sa.String(), nullable=False),
            sa.Column("nominal", sa.Integer(), nullable=False),
            sa.Column("value", sa.Float(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.PrimaryKeyConstraint("date", "char_code"),
        )
        op.create_index(
            "idx_exchange_rates_code_date",
            "exchange_rates",
            ["char_code", "date"],
            unique=False,
        )

    if "app_meta" not in tables:
        op.create_table(
            "app_meta",
            sa.Column("key", sa.String(), nullable=False),
            sa.Column("value", sa.String(), nullable=False),
            sa.PrimaryKeyConstraint("key"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "app_meta" in tables:
        op.drop_table("app_meta")
    if "exchange_rates" in tables:
        try:
            op.drop_index("idx_exchange_rates_code_date", table_name="exchange_rates")
        except Exception:
            pass
        op.drop_table("exchange_rates")

