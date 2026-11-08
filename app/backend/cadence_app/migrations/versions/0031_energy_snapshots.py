"""energy_snapshots: Garmin burn so far at a time of day (derived, safe to drop)

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-08 18:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "energy_snapshots",
        sa.Column("source_id", sa.String, sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("taken_at_local_min", sa.Integer, nullable=False),
        sa.Column("total_kcal", sa.Float, nullable=False),
        sa.Column("active_kcal", sa.Float),
        sa.Column("steps", sa.Float),
        sa.PrimaryKeyConstraint("source_id", "day", "taken_at_local_min"),
    )


def downgrade() -> None:
    op.drop_table("energy_snapshots")
