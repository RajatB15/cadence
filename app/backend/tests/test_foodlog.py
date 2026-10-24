import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from cadence_app import foodlog as F
from cadence_app.config import Settings
from cadence_app.main import create_app
from tests.test_api import MUTATE, FixedClock
from tests.test_share import api, phone, web  # noqa: F401  (fixtures)


def e(kcal, protein=None, carbs=None, fat=None, spread=20):
    return {"kcal": kcal, "protein_g": protein, "carbs_g": carbs, "fat_g": fat, "spread_pct": spread}


def synthetic_dish(i, name=None, grams=100.0, kcal100=100.0, aliases=(), portions=None):
    return {"name": name or f"Test food {i}", "unit": f"1 katori (≈{grams:g} g)" if grams != 100 else "100 g", "grams": grams,
            "per_100g": {"kcal": kcal100, "protein_g": 10.0, "carbs_g": 10.0, "fat_g": 2.0},
            "kcal": kcal100 * grams / 100, "protein_g": 10.0 * grams / 100, "carbs_g": 10.0 * grams / 100, "fat_g": 2.0 * grams / 100,
            "spread_pct": 25, "basis": "healthify", "source": "healthify", "ref_code": f"code{i:05d}", "note": "HealthifyMe: test.",
            "aliases": list(aliases), "portions": portions or [{"unit": "katori", "grams": grams}]}


def write_catalogue(directory, dishes):
    (directory / "healthifyme").mkdir(parents=True, exist_ok=True)
    (directory / "healthifyme" / "catalogue.json").write_text(json.dumps({"dishes": dishes}))


@pytest.fixture
def fenv(tmp_path):
    """The app with a synthetic food-data catalogue: 110 filler dishes plus a few named ones."""
    fd = tmp_path / "food-data"
    dishes = [synthetic_dish(i) for i in range(110)]
    dishes.append(synthetic_dish(200, "Paneer", grams=50, kcal100=265, aliases=["Cottage cheese"], portions=[{"unit": "piece", "grams": 50}, {"unit": "cup", "grams": 226}]))
    dishes.append(synthetic_dish(201, "Upma", grams=130, kcal100=85))
    write_catalogue(fd, dishes)
    secrets = tmp_path / "garmin.env"
    secrets.write_text("GARMIN_API_KEY='not-a-real-key'\n")
    app = create_app(Settings(data_dir=tmp_path / "data", secrets_file=secrets, food_data_dir=fd), FixedClock(date(2026, 10, 22)))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, fd


def dishes_of(client):
    return {d["name"]: d for d in client.get("/api/food/dishes").json()["dishes"]}


def test_empty_day_is_not_logged_rather_than_zero():
    s = F.day_summary([])
    assert s["logged"] is False and s["kcal"] is None and s["protein_g"] is None


def test_day_totals_are_a_range_and_flag_missing_macros():
    s = F.day_summary([e(500, 20, 60, 15), e(300, None, None, None, spread=30)], weight_kg=80)
    assert s["kcal"] == 800 and s["kcal_low"] == 500 * 0.8 + 300 * 0.7 and s["kcal_high"] == 500 * 1.2 + 300 * 1.3
    assert s["protein_g"] == 20 and s["partial_macros"] is True and s["protein_g_per_kg"] == 0.25


def test_average_needs_enough_logged_days():
    day = F.day_summary([e(2000, 100)])
    gap = F.day_summary([])
    assert F.average([day, day, day, gap, gap]) is None
    avg = F.average([day, day, day, day, gap])
    assert avg["days_logged"] == 4 and avg["days_covered"] == 5 and avg["kcal"] == 2000


def test_the_catalogue_loads_with_source_portions_and_aliases(fenv):
    client, _ = fenv
    d = dishes_of(client)
    paneer = d["Paneer"]
    assert len(d) == 112 and paneer["source"] == "healthify" and paneer["basis"] == "healthify" and paneer["builtin"] is True
    assert paneer["aliases"] == ["Cottage cheese"] and paneer["portions"][1] == {"unit": "cup", "grams": 226}
    assert paneer["unit_g"] == 50 and paneer["per_100g"]["kcal"] == 265 and abs(paneer["kcal"] - 132.5) < 0.01 and paneer["grams_ok"] is True
    assert "not verified" in (paneer["note"] or "") or paneer["note"] == "HealthifyMe: test."
    assert len(dishes_of(client)) == 112  # asking again adds nothing


def test_logging_by_grams_equals_logging_by_servings(fenv):
    client, _ = fenv
    paneer = dishes_of(client)["Paneer"]
    post = lambda **kw: client.post("/api/food/entries", json={"day": "2026-10-22", "meal": "lunch", "dish_id": paneer["id"], **kw}, headers=MUTATE).json()  # noqa: E731
    by_servings, by_grams, half = post(servings=2), post(grams=100), post(grams=25)
    assert by_servings["kcal"] == by_grams["kcal"] == 265 and by_servings["grams"] == by_grams["grams"] == 100
    assert half["kcal"] == 66 and half["servings"] == 0.5
    cup = post(grams=226)  # a "cup" portion from the dish's own list
    assert cup["kcal"] == 599


def test_library_round_trip_and_history_is_frozen(fenv):
    client, _ = fenv
    upma = dishes_of(client)["Upma"]
    r = client.post("/api/food/entries", json={"day": "2026-10-22", "meal": "lunch", "dish_id": upma["id"], "servings": 2}, headers=MUTATE)
    assert r.status_code == 200 and r.json()["kcal"] == 221 and r.json()["spread_pct"] == 25
    out = client.post("/api/food/entries", json={"day": "2026-10-22", "meal": "dinner", "dish_id": upma["id"], "eating_out": True}, headers=MUTATE)
    assert out.json()["spread_pct"] == F.OUT_SPREAD

    client.patch(f"/api/food/dishes/{upma['id']}", json={"kcal": 150}, headers=MUTATE)
    view = client.get("/api/food?day=2026-10-22").json()
    assert [x["kcal"] for x in view["entries"]] == [221, 110]  # logged numbers don't change
    assert view["summary"]["kcal"] == 331 and view["recent_dish_ids"] == [upma["id"]]
    assert client.delete(f"/api/food/entries/{r.json()['id']}", headers=MUTATE).status_code == 200
    assert client.delete(f"/api/food/entries/{r.json()['id']}", headers=MUTATE).status_code == 404


def test_quick_entry_custom_dish_and_validation(fenv):
    client, _ = fenv
    q = client.post("/api/food/entries", json={"day": "2026-10-22", "meal": "snack", "name": "Office thali", "kcal": 700}, headers=MUTATE)
    assert q.status_code == 200 and q.json()["protein_g"] is None and q.json()["dish_id"] is None

    made = client.post("/api/food/dishes", json={"name": "Mum's dal", "unit": "1 katori", "kcal": 140, "protein_g": 8}, headers=MUTATE)
    assert made.status_code == 200 and made.json()["builtin"] is False and made.json()["source"] == "mine"
    assert client.post("/api/food/dishes", json={"name": "Mum's dal", "unit": "x", "kcal": 1}, headers=MUTATE).status_code == 400

    def bad(**kw):
        return client.post("/api/food/entries", json={"day": "2026-10-22", "meal": "lunch", **kw}, headers=MUTATE)

    assert bad().status_code == 400 and bad(dish_id=999999).status_code == 400 and bad(name="x", kcal=-5).status_code == 422
    assert client.post("/api/food/entries", json={"day": "2026-10-23", "meal": "lunch", "name": "x", "kcal": 5}, headers=MUTATE).status_code == 400
    assert client.post("/api/food/entries", json={"day": "2026-10-22", "meal": "elevenses", "name": "x", "kcal": 5}, headers=MUTATE).status_code == 422
    assert client.post("/api/food/entries", json={"day": "2026-10-22", "meal": "lunch", "name": "x", "kcal": 5}).status_code == 403


def test_grams_need_a_dish_weight_and_your_own_dish_can_have_one(fenv):
    client, _ = fenv
    a = client.post("/api/food/dishes", json={"name": "No weight", "unit": "1 bowl", "kcal": 200}, headers=MUTATE).json()
    assert a["grams_ok"] is False and a["per_100g"] is None
    r = client.post("/api/food/entries", json={"day": "2026-10-22", "meal": "lunch", "dish_id": a["id"], "grams": 100}, headers=MUTATE)
    assert r.status_code == 400 and "serving" in r.json()["detail"]
    b = client.post("/api/food/dishes", json={"name": "With weight", "unit": "1 bowl", "kcal": 200, "protein_g": 10, "grams": 250}, headers=MUTATE).json()
    assert b["grams_ok"] is True and b["per_100g"]["kcal"] == 80
    ok = client.post("/api/food/entries", json={"day": "2026-10-22", "meal": "lunch", "dish_id": b["id"], "grams": 125}, headers=MUTATE)
    assert ok.json()["kcal"] == 100 and ok.json()["protein_g"] == 5.0


def test_catalogue_refresh_updates_untouched_dishes_and_keeps_your_edits(fenv):
    client, fd = fenv
    d = dishes_of(client)
    client.patch(f"/api/food/dishes/{d['Upma']['id']}", json={"kcal": 130, "grams": 150}, headers=MUTATE)
    changed = [synthetic_dish(i) for i in range(110)] + [synthetic_dish(200, "Paneer", grams=50, kcal100=300), synthetic_dish(201, "Upma", grams=130, kcal100=999)]
    write_catalogue(fd, changed)
    again = dishes_of(client)
    assert again["Paneer"]["per_100g"]["kcal"] == 300  # not edited: follows the catalogue
    assert again["Upma"]["kcal"] == 130 and again["Upma"]["unit_g"] == 150  # edited: yours is kept


def test_old_builtin_dishes_are_retired_but_history_and_edits_survive(tmp_path):
    import sqlite3
    fd = tmp_path / "food-data"
    secrets = tmp_path / "garmin.env"
    secrets.write_text("GARMIN_API_KEY='not-a-real-key'\n")
    settings = Settings(data_dir=tmp_path / "data", secrets_file=secrets, food_data_dir=fd)
    app = create_app(settings, FixedClock(date(2026, 10, 22)))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        # the database as the earlier version left it: built-in starter and INDB dishes, one of them edited
        db = sqlite3.connect(settings.database_path)
        cols = "name, unit, kcal, protein_g, carbs_g, fat_g, spread_pct, builtin, active, created_at, source, ref_code, edited, basis, flagged"
        db.execute(f"INSERT INTO food_dishes ({cols}) VALUES ('Old roti','1',100,3,20,1,20,1,1,'2026-10-01 00:00:00','starter',NULL,0,'estimate',0)")
        db.execute(f"INSERT INTO food_dishes ({cols}) VALUES ('Old dal','1',100,3,20,1,20,1,1,'2026-10-01 00:00:00','INDB','X1',1,'estimate',0)")
        old_roti = db.execute("SELECT id FROM food_dishes WHERE name='Old roti'").fetchone()[0]
        db.execute("INSERT INTO food_entries (day, meal, dish_id, name, servings, kcal, spread_pct, logged_at) VALUES ('2026-10-21','lunch',?, 'Old roti',1,100,20,'2026-10-21 12:00:00')", (old_roti,))
        db.commit()
        db.close()
        assert {"Old roti", "Old dal"} <= set(dishes_of(client))  # no catalogue yet: nothing is retired
        write_catalogue(fd, [synthetic_dish(i) for i in range(110)])
        F._APPLIED.clear()
        names = dishes_of(client)
        assert "Old roti" not in names and names["Old dal"]["source"] == "mine" and names["Old dal"]["builtin"] is False
        entry = client.get("/api/food?day=2026-10-21").json()["entries"][0]
        assert entry["name"] == "Old roti" and entry["kcal"] == 100 and entry["dish_id"] is None  # history keeps its own copy


def test_copy_yesterday_and_deactivated_dishes_stay_in_history(fenv):
    client, _ = fenv
    d = client.post("/api/food/dishes", json={"name": "Test dish", "unit": "1", "kcal": 100}, headers=MUTATE).json()
    client.post("/api/food/entries", json={"day": "2026-10-21", "meal": "lunch", "dish_id": d["id"]}, headers=MUTATE)
    assert client.post("/api/food/copy", json={"source": "2026-10-21", "target": "2026-10-22"}, headers=MUTATE).json() == {"copied": 1}
    client.patch(f"/api/food/dishes/{d['id']}", json={"active": False}, headers=MUTATE)
    assert d["id"] not in [x["id"] for x in client.get("/api/food/dishes").json()["dishes"]]
    assert len(client.get("/api/food?day=2026-10-22").json()["entries"]) == 1
    assert client.post("/api/food/copy", json={"source": "2026-10-21", "target": "2026-10-23"}, headers=MUTATE).status_code == 400


def test_paired_phone_can_log_food_but_not_sync(api, web):  # noqa: F811
    c = phone(api, web)
    c.get("/pair?key=tok", follow_redirects=False)
    r = c.post("/api/food/entries", json={"day": "2026-10-22", "meal": "snack", "name": "Chai and biscuits", "kcal": 150}, headers=MUTATE)
    assert r.status_code == 200 and c.get("/api/food?day=2026-10-22").json()["summary"]["kcal"] == 150
    assert c.post("/api/sync/demo", headers=MUTATE).status_code == 405
