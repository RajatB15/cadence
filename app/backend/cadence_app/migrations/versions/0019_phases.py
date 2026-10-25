"""phases: named stretches of the calendar with their own commitments

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-25 15:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "phases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("tagline", sa.String(160), nullable=False, server_default=""),
        sa.Column("emoji", sa.String(8), nullable=False, server_default=""),
        sa.Column("color", sa.String(7), nullable=False, server_default="#6cc7ff"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("pillars", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_phases_start_date", "phases", ["start_date"])


def downgrade() -> None:
    op.drop_index("ix_phases_start_date", table_name="phases")
    op.drop_table("phases")
