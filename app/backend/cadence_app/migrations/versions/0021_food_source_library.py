"""rename the dish source/basis value for catalogue dishes to "library"

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-26 12:00:00
"""
from __future__ import annotations

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Catalogue dishes carried the source's own name; every value other than your own dishes and the retired sets becomes "library".
    op.execute("UPDATE food_dishes SET source = 'library' WHERE source NOT IN ('mine', 'starter', 'INDB', 'IFCT', 'library')")
    op.execute("UPDATE food_dishes SET basis = 'library' WHERE basis NOT IN ('estimate', 'library')")
    # Older notes began with the source's name; the sentence that follows is unchanged.
    op.execute("UPDATE food_dishes SET note = 'Calculated from' || substr(note, instr(note, ' calculated from') + 16) "
               "WHERE note LIKE '%: calculated from%' AND instr(note, ' calculated from') > 0")


def downgrade() -> None:
    pass  # the old value is not restored: nothing reads it any more
