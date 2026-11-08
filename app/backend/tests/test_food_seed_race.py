"""Two first requests used to both seed the catalogue and hit the unique dish-name constraint."""
import threading
from datetime import datetime

from sqlalchemy import select

from cadence_app import foodlog
from cadence_app.db import make_engine, make_session_factory, upgrade_database
from cadence_app.models import FoodDish
from tests.test_foodlog import synthetic_dish, write_catalogue


def test_concurrent_first_calls_seed_once(tmp_path):
    fd = tmp_path / "food-data"
    write_catalogue(fd, [synthetic_dish(i) for i in range(120)])
    url = f"sqlite:///{tmp_path / 't.sqlite3'}"
    upgrade_database(url)
    factory = make_session_factory(make_engine(url))
    errors = []

    def go():
        try:
            with factory() as s:
                foodlog.ensure_catalogue(s, datetime(2026, 11, 8), fd)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    foodlog._APPLIED.clear()
    threads = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors
    with factory() as s:
        names = s.scalars(select(FoodDish.name)).all()
    assert len(names) == len(set(names)) == 120
