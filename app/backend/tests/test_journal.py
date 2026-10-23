import random
from datetime import date, timedelta

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from cadence_app.analytics import athlete as A
from cadence_app.analytics import habits as H
from cadence_app.analytics import notes
from cadence_app.analytics.insights import coach
from cadence_app.db import MIGRATIONS_DIR
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)
from tests.test_notes import ctx

D0 = date(2026, 3, 2)


def test_catalogue_checkin_and_validation(env):  # noqa: F811
    client, _ = env  # today is 2026-10-22
    j = client.get("/api/journal").json()
    assert len(j["behaviours"]) == 10 and j["checkin"] == {"day": "2026-10-21", "done": False}
    r = client.put("/api/journal/2026-10-21", json={"answers": {"alcohol": 3, "late_caffeine": 1}}, headers=MUTATE)
    assert r.status_code == 200
    answers = r.json()["answers"]
    assert answers["alcohol"] == 3 and answers["late_caffeine"] == 1 and answers["nap"] == 0  # unanswered = no
    assert r.json()["checkin"]["done"]
    assert client.get("/api/overview").json().get("journal", {"done": True})["done"] in (True, False)
    for bad in ({"late_caffeine": 2}, {"alcohol": 99}, {"nope": 1}):
        assert client.put("/api/journal/2026-10-20", json={"answers": bad}, headers=MUTATE).status_code == 400
    assert client.put("/api/journal/2026-10-22", json={"answers": {}}, headers=MUTATE).status_code == 400  # today isn't over
    assert client.put("/api/journal/2026-01-01", json={"answers": {}}, headers=MUTATE).status_code == 400  # too old

    mine = client.post("/api/journal/behaviours", json={"label": "Cold plunge", "kind": "yes_no"}, headers=MUTATE).json()
    assert mine["key"] == "my_cold_plunge" and mine["question"] == "Cold plunge?" and not mine["builtin"]
    off = client.patch("/api/journal/behaviours/screens_bed", json={"active": False}, headers=MUTATE).json()
    assert off["active"] is False
    assert client.patch("/api/journal/behaviours/alcohol", json={"label": "Booze"}, headers=MUTATE).json()["label"] == "Alcohol"
    j = client.get("/api/journal").json()
    assert len(j["behaviours"]) == 11 and j["days"][0]["answers"]["alcohol"] == 3


def test_old_tags_are_folded_into_the_journal(tmp_path):
    url = f"sqlite:///{tmp_path / 'db.sqlite3'}"
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "0004")
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO tags (day, label, created_at) VALUES ('2026-05-01', 'Big night out', '2026-05-02 08:00:00')"))
    command.upgrade(config, "head")
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT key, kind FROM behaviours")).fetchall() == [("tag_big_night_out", "yes_no")]
        assert conn.execute(sa.text("SELECT day, value FROM journal_entries")).fetchall() == [("2026-05-01", 1.0)]
        assert "tags" not in sa.inspect(conn).get_table_names()


BEHAVIOURS = [
    {"key": "alcohol", "label": "Alcohol", "kind": "count", "unit": "drinks", "active": True},
    {"key": "mobility", "label": "Mobility", "kind": "yes_no", "unit": "", "active": True},
    {"key": "nap", "label": "Nap", "kind": "yes_no", "unit": "", "active": True},
]


def journal_world(days: int = 120):
    """Two-plus drinks cost ~8 ms of next-morning HRV; naps do nothing."""
    rng = random.Random(11)
    ds = [D0 + timedelta(days=i) for i in range(days)]
    drinks = {d: rng.choice([0, 0, 0, 1, 2, 3]) for d in ds}
    naps = {d: float(rng.random() < 0.4) for d in ds}
    hrv = {d + timedelta(days=1): 60 - (8 if drinks[d] >= 2 else 0) + rng.gauss(0, 2) for d in ds}
    answers = {"alcohol": drinks, "nap": naps, "mobility": {d: 0.0 for d in ds[:5]}}
    return ds, answers, {"hrv": hrv, "resting_hr": {d: 50.0 + rng.gauss(0, 1) for d in hrv}}


def test_habit_insights_find_the_real_cost_and_ignore_noise():
    ds, answers, series = journal_world()
    covs = {"weekend": {d: float(d.weekday() >= 5) for d in ds}}
    r = H.insights(BEHAVIOURS, answers, series, covs)
    progress = {p["key"]: p for p in r["progress"]}
    assert progress["alcohol"]["ready"] and progress["alcohol"]["yes_label"] == "2+ drinks"
    assert not progress["mobility"]["ready"] and progress["mobility"]["no"] == 5
    best = H.strongest(r["effects"])
    assert set(best) == {"alcohol"} and best["alcohol"].extra["outcome"] == "hrv"
    assert best["alcohol"].diff < -6 and H.worse(best["alcohol"])


def test_habits_reach_the_coach_and_the_day_page():
    ds, answers, series = journal_world()
    c = ctx([], series, days=121, journal={"behaviours": BEHAVIOURS, "answers": answers})
    assert any(f["id"] == "habit_alcohol" and f["severity"] == "warn" for f in coach(c))
    drink_day = next(d for d in ds[-30:] if answers["alcohol"][d] >= 2)
    day = notes.day(c, drink_day + timedelta(days=1))
    assert any(n["id"] == "habit_alcohol" for n in day["notes"])
    assert any("drinks (alcohol)" in x for x in notes.contributors(c, drink_day + timedelta(days=1)))
    assert A.Effect  # module import used
