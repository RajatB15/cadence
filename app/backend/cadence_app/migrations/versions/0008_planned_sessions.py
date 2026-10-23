"""planned sessions

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-23 21:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planned_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("sport", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("option_key", sa.String(length=48), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("predicted", sa.Text(), nullable=False),
        sa.Column("strength_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_planned_sessions_day", "planned_sessions", ["day"])


def downgrade() -> None:
    op.drop_index("ix_planned_sessions_day", table_name="planned_sessions")
    op.drop_table("planned_sessions")
