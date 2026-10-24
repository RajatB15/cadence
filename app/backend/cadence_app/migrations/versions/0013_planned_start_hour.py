"""planned sessions: the hour you plan to start (for the weather forecast)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-24 23:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("planned_sessions") as batch:
        batch.add_column(sa.Column("start_hour", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("planned_sessions") as batch:
        batch.drop_column("start_hour")
