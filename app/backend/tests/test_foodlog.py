from datetime import date

from cadence_app import foodlog as F
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)
from tests.test_share import api, phone, web  # noqa: F401  (fixtures)


def e(kcal, protein=None, carbs=None, fat=None, spread=20):
    return {"kcal": kcal, "protein_g": protein, "carbs_g": carbs, "fat_g": fat, "spread_pct": spread}


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


def test_library_round_trip_and_history_is_frozen(env):  # noqa: F811
    client, _ = env  # fixed clock: 2026-10-22
    dishes = client.get("/api/food/dishes").json()["dishes"]
    roti = next(d for d in dishes if d["name"] == "Roti / chapati")
    assert len(dishes) > 50 and all(d["builtin"] for d in dishes)

    r = client.post("/api/food/entries", json={"day": "2026-10-22", "meal": "lunch", "dish_id": roti["id"], "servings": 2}, headers=MUTATE)
    assert r.status_code == 200 and r.json()["kcal"] == 220 and r.json()["spread_pct"] == F.HOME_SPREAD
    out = client.post("/api/food/entries", json={"day": "2026-10-22", "meal": "dinner", "dish_id": roti["id"], "eating_out": True}, headers=MUTATE)
    assert out.json()["spread_pct"] == F.OUT_SPREAD

    client.patch(f"/api/food/dishes/{roti['id']}", json={"kcal": 150}, headers=MUTATE)
    view = client.get("/api/food?day=2026-10-22").json()
    assert [x["kcal"] for x in view["entries"]] == [220, 110]  # logged numbers don't change
    assert view["summary"]["kcal"] == 330 and view["recent_dish_ids"] == [roti["id"]]

    assert client.delete(f"/api/food/entries/{r.json()['id']}", headers=MUTATE).status_code == 200
    assert client.delete(f"/api/food/entries/{r.json()['id']}", headers=MUTATE).status_code == 404


def test_quick_entry_custom_dish_and_validation(env):  # noqa: F811
    client, _ = env
    q = client.post("/api/food/entries", json={"day": "2026-10-22", "meal": "snack", "name": "Office thali", "kcal": 700}, headers=MUTATE)
    assert q.status_code == 200 and q.json()["protein_g"] is None and q.json()["dish_id"] is None

    made = client.post("/api/food/dishes", json={"name": "Mum's dal", "unit": "1 katori", "kcal": 140, "protein_g": 8}, headers=MUTATE)
    assert made.status_code == 200 and made.json()["builtin"] is False
    assert client.post("/api/food/dishes", json={"name": "Mum's dal", "unit": "x", "kcal": 1}, headers=MUTATE).status_code == 400

    bad = lambda **kw: client.post("/api/food/entries", json={"day": "2026-10-22", "meal": "lunch", **kw}, headers=MUTATE)
    assert bad().status_code == 400  # neither a dish nor a name + calories
    assert bad(dish_id=999999).status_code == 400
    assert bad(name="x", kcal=-5).status_code == 422
    assert client.post("/api/food/entries", json={"day": "2026-10-23", "meal": "lunch", "name": "x", "kcal": 5}, headers=MUTATE).status_code == 400
    assert client.post("/api/food/entries", json={"day": "2026-10-22", "meal": "elevenses", "name": "x", "kcal": 5}, headers=MUTATE).status_code == 422
    assert client.post("/api/food/entries", json={"day": "2026-10-22", "meal": "lunch", "name": "x", "kcal": 5}).status_code == 403


def test_copy_yesterday_and_deactivated_dishes_stay_in_history(env):  # noqa: F811
    client, _ = env
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


def test_starter_catalogue_file_is_sane():
    dishes = F.starter_dishes()
    names = [d["name"] for d in dishes]
    assert len(names) == len(set(names)) and len(dishes) > 50
    assert all(d["unit"] and 0 <= d["kcal"] <= 1500 and min(d["protein_g"], d["carbs_g"], d["fat_g"]) >= 0 for d in dishes)
