"""gym: workouts you did (gym_workouts)

Additive: one new table. Entries are JSON validated in code. Keyed by plan id with no foreign key so deleting a plan never loses a log.

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-10 22:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gym_workouts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("day", sa.Date, nullable=False, index=True),
        sa.Column("plan_id", sa.Integer, nullable=True, index=True),
        sa.Column("session_id", sa.Integer, nullable=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("setting", sa.String(8), nullable=False, server_default="gym"),
        sa.Column("duration_s", sa.Integer, nullable=True),
        sa.Column("entries", sa.Text, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("gym_workouts")
