"""Indexes on computed_at of the derived caches so data_version can count/max them cheaply

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-05 10:00:00
"""
from __future__ import annotations

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_activity_analyses_computed_at", "activity_analyses", ["computed_at"])
    op.create_index("ix_day_hr_histograms_computed_at", "day_hr_histograms", ["computed_at"])


def downgrade() -> None:
    op.drop_index("ix_day_hr_histograms_computed_at", table_name="day_hr_histograms")
    op.drop_index("ix_activity_analyses_computed_at", table_name="activity_analyses")
