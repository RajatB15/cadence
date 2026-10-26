"""time_off: travel, holiday, illness and injury periods the plan works around

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-26 10:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "time_off",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("activity", sa.String(8), nullable=True),
        sa.Column("severity", sa.Integer(), nullable=True),
        sa.Column("return_weeks", sa.Integer(), nullable=True),
        sa.Column("return_start_pct", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_time_off_start_date", "time_off", ["start_date"])


def downgrade() -> None:
    op.drop_index("ix_time_off_start_date", table_name="time_off")
    op.drop_table("time_off")
