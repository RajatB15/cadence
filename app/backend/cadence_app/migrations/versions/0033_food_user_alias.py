"""food: your own names for dishes (food_user_alias)

Additive: one new table. `dish_id` is SET NULL (not cascade) because library dishes are deleted and re-added when the
private catalogue is re-seeded; `ref_code` lets the alias find the new row again, so your names are never lost.

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-08 22:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "food_user_alias",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("dish_id", sa.Integer, sa.ForeignKey("food_dishes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ref_code", sa.String(24), nullable=True),
        sa.Column("alias", sa.String(60), nullable=False),
        sa.Column("folded", sa.String(120), nullable=False),
        sa.Column("preferred", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("use_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("dish_id", "folded", name="ux_food_user_alias_dish_folded"),
    )
    op.create_index("ix_food_user_alias_ref_code", "food_user_alias", ["ref_code"])


def downgrade() -> None:
    op.drop_index("ix_food_user_alias_ref_code", table_name="food_user_alias")
    op.drop_table("food_user_alias")
