"""wellbeing: a daily self-report of feel, soreness, pain, illness and life stress

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-24 21:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wellbeing",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("feel", sa.Integer(), nullable=True),
        sa.Column("soreness", sa.Integer(), nullable=True),
        sa.Column("pain_level", sa.Integer(), nullable=True),
        sa.Column("pain_area", sa.String(length=40), nullable=True),
        sa.Column("illness", sa.Integer(), nullable=True),
        sa.Column("life_stress", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("day"),
    )


def downgrade() -> None:
    op.drop_table("wellbeing")
