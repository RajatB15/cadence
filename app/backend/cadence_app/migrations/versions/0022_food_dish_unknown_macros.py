"""dishes may have unknown macros (a label or quick entry that did not give them)

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-26 14:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("food_dishes") as t:
        for column in ("protein_g", "carbs_g", "fat_g"):
            t.alter_column(column, existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE food_dishes SET protein_g = 0 WHERE protein_g IS NULL")
    op.execute("UPDATE food_dishes SET carbs_g = 0 WHERE carbs_g IS NULL")
    op.execute("UPDATE food_dishes SET fat_g = 0 WHERE fat_g IS NULL")
    with op.batch_alter_table("food_dishes") as t:
        for column in ("protein_g", "carbs_g", "fat_g"):
            t.alter_column(column, existing_type=sa.Float(), nullable=False)
