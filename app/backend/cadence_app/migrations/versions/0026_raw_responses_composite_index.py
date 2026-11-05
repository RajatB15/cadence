"""raw_responses: composite index for per-dataset replay and cache keys

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-05 09:00:00
"""
from __future__ import annotations

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

INDEX = "ix_raw_responses_source_dataset_fetched"


def upgrade() -> None:
    op.create_index(INDEX, "raw_responses", ["source_id", "dataset", "fetched_at"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name="raw_responses")
