"""food dishes: other names (search aliases) and household portions with their weights

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-25 12:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("food_dishes") as batch:
        batch.add_column(sa.Column("aliases", sa.Text(), nullable=True))
        batch.add_column(sa.Column("portions", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("food_dishes") as batch:
        batch.drop_column("portions")
        batch.drop_column("aliases")
