"""reading_items: what you did with each daily reading card

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-26 16:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reading_items",
        sa.Column("card_id", sa.String(80), primary_key=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="shown"),
        sa.Column("picked_day", sa.Date(), nullable=True),
        sa.Column("why", sa.String(200), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_reading_items_picked_day", "reading_items", ["picked_day"])


def downgrade() -> None:
    op.drop_index("ix_reading_items_picked_day", table_name="reading_items")
    op.drop_table("reading_items")
