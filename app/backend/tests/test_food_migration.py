"""Migration 0021 renames the source of catalogue dishes without touching your own dishes."""
import sqlite3

from alembic import command
from alembic.config import Config

from cadence_app.db import MIGRATIONS_DIR


def test_catalogue_dishes_become_library_and_your_own_stay(tmp_path):
    db = tmp_path / "m.sqlite3"
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(config, "0020")
    con = sqlite3.connect(db)
    cols = "name, unit, kcal, protein_g, carbs_g, fat_g, spread_pct, builtin, active, source, basis, note, flagged, edited, created_at"
    rows = [("Old catalogue dish", "oldsrc", "oldsrc", "Oldsrc: calculated from a recipe in its database; not verified."),
            ("My dish", "mine", "estimate", "Edited by you."), ("Retired set", "INDB", "estimate", None)]
    for name, source, basis, note in rows:
        con.execute(f"INSERT INTO food_dishes ({cols}) VALUES (?, '1', 100, 1, 1, 1, 20, 0, 1, ?, ?, ?, 0, 0, '2026-10-01')", (name, source, basis, note))
    con.commit()
    con.close()
    command.upgrade(config, "head")
    got = {r[0]: r[1:] for r in sqlite3.connect(db).execute("SELECT name, source, basis, note FROM food_dishes")}
    assert got["Old catalogue dish"] == ("library", "library", "Calculated from a recipe in its database; not verified.")
    assert got["My dish"] == ("mine", "estimate", "Edited by you.")
    assert got["Retired set"] == ("INDB", "estimate", None)
