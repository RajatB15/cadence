from datetime import date

import pytest
from sqlalchemy import select

from cadence_app import profile
from cadence_app.db import make_engine, make_session_factory, upgrade_database


@pytest.fixture
def session(tmp_path):
    url = f"sqlite:///{tmp_path / 'db.sqlite3'}"
    upgrade_database(url)
    factory = make_session_factory(make_engine(url))
    with factory() as s:
        yield s


def test_round_trips_height_birth_date_and_sex(session):
    assert profile.load(session) is None
    saved = profile.save(session, 178.0, date(1990, 5, 1), "male")
    assert saved == {"height_cm": 178.0, "birth_date": date(1990, 5, 1), "sex": "male"}
    loaded = profile.load(session)
    assert loaded == saved
    # Saving again overwrites rather than duplicating the AppSetting row.
    profile.save(session, 180.0, date(1990, 5, 1), "male")
    assert profile.load(session)["height_cm"] == 180.0


@pytest.mark.parametrize(
    "height,birth,sex",
    [(50.0, date(1990, 1, 1), "male"), (178.0, date(2999, 1, 1), "male"), (178.0, date(1990, 1, 1), "other")],
)
def test_rejects_out_of_range_values(session, height, birth, sex):
    with pytest.raises(ValueError):
        profile.save(session, height, birth, sex)


def test_age_years_accounts_for_leap_years_reasonably():
    assert profile.age_years(date(1996, 10, 24), date(2026, 10, 24)) == pytest.approx(30.0, abs=0.01)
    assert profile.age_years(date(2026, 1, 1), date(2026, 1, 1)) == 0.0
