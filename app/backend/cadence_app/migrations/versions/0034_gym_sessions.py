"""gym: saved gym sessions (gym_sessions)

Additive: one new table. Steps are JSON (exercises, rests and nested groups) validated in code; the exercise library itself is
a bundled file, not stored. Planned copies live in planned_sessions as ordinary strength sessions.

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-10 20:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gym_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("setting", sa.String(8), nullable=False, server_default="gym"),
        sa.Column("format", sa.String(16), nullable=False, server_default="straight"),
        sa.Column("steps", sa.Text, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("gym_sessions")
