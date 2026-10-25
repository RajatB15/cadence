"""food micronutrients and saved meals

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-26 10:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("food_dishes") as t:
        t.add_column(sa.Column("micros_100g", sa.Text(), nullable=True))
    with op.batch_alter_table("food_entries") as t:
        t.add_column(sa.Column("micros", sa.Text(), nullable=True))
    op.create_table(
        "food_meals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "food_meal_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("meal_id", sa.Integer(), sa.ForeignKey("food_meals.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dish_id", sa.Integer(), sa.ForeignKey("food_dishes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("servings", sa.Float(), nullable=False),
        sa.Column("grams", sa.Float(), nullable=True),
        sa.Column("kcal", sa.Float(), nullable=False),
        sa.Column("protein_g", sa.Float(), nullable=True),
        sa.Column("carbs_g", sa.Float(), nullable=True),
        sa.Column("fat_g", sa.Float(), nullable=True),
        sa.Column("spread_pct", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("micros", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("food_meal_items")
    op.drop_table("food_meals")
    with op.batch_alter_table("food_entries") as t:
        t.drop_column("micros")
    with op.batch_alter_table("food_dishes") as t:
        t.drop_column("micros_100g")
