"""dataset_states: per-request bad-body attempt counters (JSON)

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-05 11:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dataset_states", sa.Column("item_failures", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("dataset_states", "item_failures")
