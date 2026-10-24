"""planned sessions: the workout sent to Garmin Connect

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-25 13:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("planned_sessions") as batch:
        batch.add_column(sa.Column("garmin_workout_id", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("garmin_schedule_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("planned_sessions") as batch:
        batch.drop_column("garmin_schedule_id")
        batch.drop_column("garmin_workout_id")
