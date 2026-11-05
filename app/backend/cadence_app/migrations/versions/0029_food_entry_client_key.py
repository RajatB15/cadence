"""food_entries: optional client idempotency key so a retried POST does not log twice

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-05 12:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("food_entries", sa.Column("client_key", sa.String(64), nullable=True))
    op.create_index("ux_food_entries_client_key", "food_entries", ["client_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_food_entries_client_key", table_name="food_entries")
    op.drop_column("food_entries", "client_key")
