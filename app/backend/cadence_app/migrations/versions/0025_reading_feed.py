"""reading_feed: recent open-access papers for the reading page

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-26 18:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reading_feed",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("topic", sa.String(24), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("journal", sa.String(200), nullable=False, server_default=""),
        sa.Column("published", sa.Date(), nullable=False),
        sa.Column("evidence", sa.String(16), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("licence", sa.String(40), nullable=False, server_default=""),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_reading_feed_topic", "reading_feed", ["topic"])
    op.create_index("ix_reading_feed_published", "reading_feed", ["published"])


def downgrade() -> None:
    op.drop_index("ix_reading_feed_published", table_name="reading_feed")
    op.drop_index("ix_reading_feed_topic", table_name="reading_feed")
    op.drop_table("reading_feed")
