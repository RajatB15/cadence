"""cached all-day heart-rate histograms for strain

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-23 18:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "day_hr_histograms",
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("outside", sa.Text(), nullable=False),
        sa.Column("inside", sa.Text(), nullable=False),
        sa.Column("samples", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("source_id", "day"),
    )


def downgrade() -> None:
    op.drop_table("day_hr_histograms")
