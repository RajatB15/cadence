"""food dishes: where a dish came from (starter, INDB, IFCT or your own) and its source code

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-24 23:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("food_dishes") as batch:
        batch.add_column(sa.Column("source", sa.String(length=16), nullable=False, server_default="mine"))
        batch.add_column(sa.Column("ref_code", sa.String(length=24), nullable=True))
    op.execute("UPDATE food_dishes SET source = 'starter' WHERE builtin = 1")
    op.create_index("ix_food_dishes_source_ref", "food_dishes", ["source", "ref_code"])


def downgrade() -> None:
    op.drop_index("ix_food_dishes_source_ref", table_name="food_dishes")
    with op.batch_alter_table("food_dishes") as batch:
        batch.drop_column("ref_code")
        batch.drop_column("source")
