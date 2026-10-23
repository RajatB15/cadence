"""journal: behaviours and daily answers (replaces the unused tags table)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23 14:00:00
"""
from __future__ import annotations

import re
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "behaviours",
        sa.Column("key", sa.String(length=48), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("question", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("behaviour_key", sa.String(length=48), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("answered_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["behaviour_key"], ["behaviours.key"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("day", "behaviour_key"),
    )
    op.create_index("ix_journal_entries_day", "journal_entries", ["day"])
    op.create_index("ix_journal_entries_behaviour_key", "journal_entries", ["behaviour_key"])

    # Fold any old tags in as custom yes/no behaviours, so nothing logged is lost.
    bind = op.get_bind()
    tags = bind.execute(sa.text("SELECT day, label, created_at FROM tags")).fetchall()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")  # SQLAlchemy's SQLite DateTime format
    for label in sorted({t.label for t in tags}):
        key = "tag_" + (re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "tag")[:40]
        bind.execute(
            sa.text("INSERT OR IGNORE INTO behaviours (key, label, question, kind, unit, active, builtin, sort, created_at) "
                    "VALUES (:k, :l, :q, 'yes_no', '', 1, 0, 200, :c)"),
            {"k": key, "l": label[:80], "q": f"{label[:150]}?", "c": now},
        )
        for t in (t for t in tags if t.label == label):
            bind.execute(
                sa.text("INSERT OR IGNORE INTO journal_entries (day, behaviour_key, value, answered_at) VALUES (:d, :k, 1, :a)"),
                {"d": t.day, "k": key, "a": t.created_at},
            )
    op.drop_index("ix_tags_day", table_name="tags")
    op.drop_table("tags")


def downgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("label", sa.String(length=48), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("day", "label"),
    )
    op.create_index("ix_tags_day", "tags", ["day"])
    op.drop_index("ix_journal_entries_behaviour_key", table_name="journal_entries")
    op.drop_index("ix_journal_entries_day", table_name="journal_entries")
    op.drop_table("journal_entries")
    op.drop_table("behaviours")
