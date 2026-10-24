"""goals: races, performances, distances and weight targets

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-24 18:00:00
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

RACES = {"5k": ("5 km", 5000.0), "10k": ("10 km", 10000.0), "half": ("Half marathon", 21097.5), "marathon": ("Marathon", 42195.0)}


def upgrade() -> None:
    goals = op.create_table(
        "goals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("sport", sa.String(length=16), nullable=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("spec", sa.Text(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("start_value", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_goals_target_date", "goals", ["target_date"])
    op.create_index("ix_goals_status", "goals", ["status"])

    # Move the two single-value goals that lived in app_settings into the table.
    bind = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = {k: v for k, v in bind.execute(sa.text("SELECT key, value FROM app_settings WHERE key IN ('training_goal', 'weight_goal_kg')"))}
    inserts = []
    if "training_goal" in rows:
        try:
            raw = json.loads(rows["training_goal"])
            label, metres = RACES[raw["distance"]]
            inserts.append({"kind": "race", "sport": "run", "title": label, "target_date": datetime.fromisoformat(raw["date"]).date(),
                            "spec": json.dumps({"distance_m": metres, "key": raw["distance"], "label": label, "target_s": raw.get("target_s")}),
                            "status": "active", "start_value": None, "created_at": now, "closed_at": None})
        except (ValueError, KeyError, TypeError):
            pass
    if "weight_goal_kg" in rows:
        try:
            kg = float(rows["weight_goal_kg"])
            inserts.append({"kind": "weight", "sport": None, "title": f"{kg:g} kg", "target_date": None, "spec": json.dumps({"target_kg": kg}),
                            "status": "active", "start_value": None, "created_at": now, "closed_at": None})
        except ValueError:
            pass
    if inserts:
        op.bulk_insert(goals, inserts)
    bind.execute(sa.text("DELETE FROM app_settings WHERE key IN ('training_goal', 'weight_goal_kg')"))


def downgrade() -> None:
    op.drop_index("ix_goals_status", table_name="goals")
    op.drop_index("ix_goals_target_date", table_name="goals")
    op.drop_table("goals")
