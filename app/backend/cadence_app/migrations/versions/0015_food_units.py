"""food: grams as the standard unit (weight of one serving, per-100 g nutrition, basis) and logged grams

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-25 09:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("food_dishes") as batch:
        batch.add_column(sa.Column("unit_g", sa.Float(), nullable=True))
        batch.add_column(sa.Column("kcal_100g", sa.Float(), nullable=True))
        batch.add_column(sa.Column("protein_100g", sa.Float(), nullable=True))
        batch.add_column(sa.Column("carbs_100g", sa.Float(), nullable=True))
        batch.add_column(sa.Column("fat_100g", sa.Float(), nullable=True))
        batch.add_column(sa.Column("basis", sa.String(length=16), nullable=False, server_default="estimate"))
        batch.add_column(sa.Column("note", sa.String(length=240), nullable=True))
        batch.add_column(sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("edited", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("food_entries") as batch:
        batch.add_column(sa.Column("grams", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("food_entries") as batch:
        batch.drop_column("grams")
    with op.batch_alter_table("food_dishes") as batch:
        for col in ("edited", "flagged", "note", "basis", "fat_100g", "carbs_100g", "protein_100g", "kcal_100g", "unit_g"):
            batch.drop_column(col)
