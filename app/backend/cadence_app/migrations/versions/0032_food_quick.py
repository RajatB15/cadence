"""food quick logging: eaten_at, soft delete, source, barcode, pinned, portion memory

Additive only. SQLite ADD COLUMN never rebuilds a table, so food_entries/food_dishes keep their rows and nothing
cascades (foreign keys stay as they are). The downgrade uses DROP COLUMN for the same reason.

Existing entries get `eaten_at` from a meal-time default and are marked `eaten_at_est`, so display can order them but
the energy card never treats the default as when something was really eaten.

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-08 20:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

MEAL_DEFAULTS = {"breakfast": "08:00:00", "lunch": "13:00:00", "snack": "16:30:00", "dinner": "20:00:00"}


def upgrade() -> None:
    op.add_column("food_entries", sa.Column("eaten_at", sa.Time, nullable=True))
    op.add_column("food_entries", sa.Column("eaten_at_est", sa.Boolean, nullable=False, server_default="0"))
    op.add_column("food_entries", sa.Column("deleted_at", sa.DateTime, nullable=True))
    op.add_column("food_entries", sa.Column("source", sa.String(12), nullable=False, server_default="manual"))
    op.create_index("ix_food_entries_deleted_at", "food_entries", ["deleted_at"])
    op.add_column("food_dishes", sa.Column("barcode", sa.String(20), nullable=True))
    op.add_column("food_dishes", sa.Column("pinned", sa.Boolean, nullable=False, server_default="0"))
    op.create_index("ux_food_dishes_barcode", "food_dishes", ["barcode"], unique=True, sqlite_where=sa.text("barcode IS NOT NULL"))
    op.add_column("food_meals", sa.Column("pinned", sa.Boolean, nullable=False, server_default="0"))
    op.create_table(
        "food_portion_memory",
        sa.Column("dish_id", sa.Integer, sa.ForeignKey("food_dishes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("servings", sa.Float, nullable=False),
        sa.Column("unit", sa.String(40)),
        sa.Column("grams", sa.Float),
        sa.Column("n", sa.Integer, nullable=False, server_default="1"),
        sa.Column("streak", sa.Integer, nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    for meal, at in MEAL_DEFAULTS.items():
        op.execute(sa.text("UPDATE food_entries SET eaten_at = :at, eaten_at_est = 1 WHERE meal = :meal AND eaten_at IS NULL").bindparams(at=at, meal=meal))


def downgrade() -> None:
    op.drop_table("food_portion_memory")
    op.drop_index("ux_food_dishes_barcode", table_name="food_dishes")
    op.execute("ALTER TABLE food_meals DROP COLUMN pinned")
    op.execute("ALTER TABLE food_dishes DROP COLUMN pinned")
    op.execute("ALTER TABLE food_dishes DROP COLUMN barcode")
    # Soft-deleted rows were removed by the user: do not bring them back when the column that hides them goes away.
    op.execute("DELETE FROM food_entries WHERE deleted_at IS NOT NULL")
    op.drop_index("ix_food_entries_deleted_at", table_name="food_entries")
    for col in ("source", "deleted_at", "eaten_at_est", "eaten_at"):
        op.execute(f"ALTER TABLE food_entries DROP COLUMN {col}")
