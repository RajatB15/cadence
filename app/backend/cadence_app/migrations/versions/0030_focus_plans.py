"""focus_plans: the four-week focus accepted from the Improve page

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-08 12:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "focus_plans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("metric", sa.String(12), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("priorities", sa.Text, nullable=False, server_default="[]"),
        sa.Column("baseline", sa.Text, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(12), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_focus_plans_metric", "focus_plans", ["metric"])
    op.create_index("ix_focus_plans_start_date", "focus_plans", ["start_date"])


def downgrade() -> None:
    op.drop_index("ix_focus_plans_start_date", table_name="focus_plans")
    op.drop_index("ix_focus_plans_metric", table_name="focus_plans")
    op.drop_table("focus_plans")
