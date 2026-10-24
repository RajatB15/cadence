"""events: several activities grouped into one trek, expedition or multisport day

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-25 14:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "event_activities",
        sa.Column("source_id", sa.String(32), primary_key=True),
        sa.Column("source_record_id", sa.String(64), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_event_activities_event_id", "event_activities", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_event_activities_event_id", table_name="event_activities")
    op.drop_table("event_activities")
    op.drop_table("events")
