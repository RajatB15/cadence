"""Micronutrients and saved meals, with synthetic dishes only."""
from cadence_app import nutrients as N
from tests.test_api import MUTATE
from tests.test_foodlog import dishes_of, fenv, synthetic_dish, write_catalogue  # noqa: F401  (fixtures)

DAY = "2026-10-22"


def with_micros(dish, **m):
    return {**dish, "micros_per_100g": m}


def test_pick_keeps_tracked_nutrients_with_matching_units_and_leaves_gaps_out():
    table = {"Fibre": [3.5, "g"], "Sodium": [120.0, "mg"], "Vitamin A": [40, "ug"], "Iron": [2.0, "g"], "Zinc": [None, "mg"], "Choline": [9, "mg"]}
    assert N.pick(table) == {"fibre_g": 3.5, "sodium_mg": 120.0, "vitamin_a_ug": 40.0}  # wrong unit, empty and untracked are dropped
    assert N.pick(None) == {}


def test_summary_says_how_many_foods_reported_each_nutrient_and_never_invents_zero():
    rows = {r["key"]: r for r in N.summarise([{"fibre_g": 4.0, "sodium_mg": 300}, {"fibre_g": 2.5}, None])}
    assert rows["fibre_g"]["amount"] == 6.5 and rows["fibre_g"]["foods_with"] == 2 and rows["fibre_g"]["foods"] == 3
    assert rows["fibre_g"]["pct"] == 26  # of the 25 g reference
    assert rows["iron_mg"]["amount"] is None and rows["iron_mg"]["foods_with"] == 0
    assert N.summarise([]) == []


def test_logged_food_carries_scaled_micros_into_the_day_view(tmp_path, fenv):  # noqa: F811
    client, fd = fenv
    write_catalogue(fd, [with_micros(synthetic_dish(i), fibre_g=2.0, sodium_mg=100.0) for i in range(110)]
                    + [with_micros(synthetic_dish(300, "Dal", grams=200, kcal100=100), fibre_g=5.0, iron_mg=2.0)])
    dal = dishes_of(client)["Dal"]
    assert dal["micros_per_100g"] == {"fibre_g": 5.0, "iron_mg": 2.0}
    entry = client.post("/api/food/entries", json={"day": DAY, "meal": "lunch", "dish_id": dal["id"], "servings": 1.5}, headers=MUTATE).json()
    assert entry["micros"] == {"fibre_g": 15.0, "iron_mg": 6.0}  # 300 g
    client.post("/api/food/entries", json={"day": DAY, "meal": "dinner", "name": "Restaurant thali", "kcal": 700}, headers=MUTATE)
    rows = {r["key"]: r for r in client.get(f"/api/food?day={DAY}").json()["micros"]}
    assert rows["fibre_g"]["amount"] == 15.0 and rows["fibre_g"]["foods_with"] == 1 and rows["fibre_g"]["foods"] == 2
    assert rows["zinc_mg"]["amount"] is None


def test_changing_the_amount_scales_everything_in_the_entry(fenv):  # noqa: F811
    client, _ = fenv
    upma = dishes_of(client)["Upma"]
    e = client.post("/api/food/entries", json={"day": DAY, "meal": "lunch", "dish_id": upma["id"], "servings": 1}, headers=MUTATE).json()
    r = client.patch(f"/api/food/entries/{e['id']}", json={"servings": 2}, headers=MUTATE)
    assert r.status_code == 200 and r.json()["kcal"] == 221 and r.json()["grams"] == e["grams"] * 2
    assert client.patch(f"/api/food/entries/{e['id']}", json={"servings": 0}, headers=MUTATE).status_code == 422
    assert client.patch("/api/food/entries/99999", json={"servings": 1}, headers=MUTATE).status_code == 404


def test_save_a_meal_from_entries_and_log_it_again_scaled(fenv):  # noqa: F811
    client, _ = fenv
    d = dishes_of(client)
    ids = [client.post("/api/food/entries", json={"day": DAY, "meal": "breakfast", "dish_id": d[n]["id"], "servings": s}, headers=MUTATE).json()["id"]
           for n, s in (("Upma", 1), ("Paneer", 2))]
    quick = client.post("/api/food/entries", json={"day": DAY, "meal": "breakfast", "name": "Chai", "kcal": 80}, headers=MUTATE).json()["id"]
    saved = client.post("/api/food/meals", json={"name": "Usual breakfast", "entry_ids": [*ids, quick]}, headers=MUTATE)
    assert saved.status_code == 200
    meal = saved.json()
    assert [i["name"] for i in meal["items"]] == ["Upma", "Paneer", "Chai"] and meal["kcal"] == 456  # 110.5 + 265 + 80
    assert client.post("/api/food/meals", json={"name": "usual BREAKFAST", "entry_ids": ids}, headers=MUTATE).status_code == 400  # names are unique
    assert client.post("/api/food/meals", json={"name": "Ghost", "entry_ids": [99999]}, headers=MUTATE).status_code == 400

    r = client.post(f"/api/food/meals/{meal['id']}/log", json={"day": "2026-10-21", "meal": "lunch", "scale": 0.5}, headers=MUTATE)
    logged = r.json()["entries"]
    assert [e["name"] for e in logged] == ["Upma", "Paneer", "Chai"] and [e["kcal"] for e in logged] == [55, 132, 40]
    assert client.get("/api/food?day=2026-10-21").json()["summary"]["kcal"] == 227
    assert client.get("/api/food/meals").json()["meals"][0]["last_used"] is not None
    assert client.post(f"/api/food/meals/{meal['id']}/log", json={"day": "2026-10-23", "meal": "lunch"}, headers=MUTATE).status_code == 400  # future


def test_meal_uses_the_dish_as_it_is_today_and_survives_a_removed_dish(fenv):  # noqa: F811
    client, _ = fenv
    upma = dishes_of(client)["Upma"]
    e = client.post("/api/food/entries", json={"day": DAY, "meal": "breakfast", "dish_id": upma["id"], "servings": 1}, headers=MUTATE).json()
    meal = client.post("/api/food/meals", json={"name": "Upma plate", "entry_ids": [e["id"]]}, headers=MUTATE).json()
    client.patch(f"/api/food/dishes/{upma['id']}", json={"kcal": 200}, headers=MUTATE)
    assert client.get("/api/food/meals").json()["meals"][0]["kcal"] == 200  # follows your edit of the dish
    client.patch(f"/api/food/dishes/{upma['id']}", json={"active": False}, headers=MUTATE)
    assert client.get("/api/food/meals").json()["meals"][0]["kcal"] == 110  # falls back to what was saved
    assert client.patch(f"/api/food/meals/{meal['id']}", json={"name": "Weekday upma"}, headers=MUTATE).json()["name"] == "Weekday upma"
    assert client.delete(f"/api/food/meals/{meal['id']}", headers=MUTATE).status_code == 200
    assert client.get("/api/food/meals").json()["meals"] == []
    assert client.delete(f"/api/food/meals/{meal['id']}", headers=MUTATE).status_code == 404


def test_quick_entry_is_remembered_as_a_dish_and_unknown_macros_stay_unknown(fenv):  # noqa: F811
    client, _ = fenv
    q = client.post("/api/food/entries", json={"day": DAY, "meal": "dinner", "name": "Office thali", "kcal": 700, "protein_g": 22}, headers=MUTATE).json()
    dish = dishes_of(client)["Office thali"]
    assert q["saved_dish"] and q["dish_id"] == dish["id"] and dish["kcal"] == 700 and dish["protein_g"] == 22
    assert dish["carbs_g"] is None and dish["fat_g"] is None and dish["unit"] == "1 serving"  # not given, so unknown, not zero
    again = client.post("/api/food/entries", json={"day": DAY, "meal": "lunch", "dish_id": dish["id"], "servings": 2}, headers=MUTATE).json()
    assert again["kcal"] == 1400 and again["protein_g"] == 44 and again["carbs_g"] is None and again["fat_g"] is None
    dup = client.post("/api/food/entries", json={"day": DAY, "meal": "lunch", "name": "office THALI", "kcal": 650}, headers=MUTATE).json()
    assert dup["saved_dish"] is False and dup["dish_id"] is None  # a dish with that name exists: only logged
    skip = client.post("/api/food/entries", json={"day": DAY, "meal": "lunch", "name": "One-off", "kcal": 300, "save_dish": False}, headers=MUTATE).json()
    assert skip["saved_dish"] is False and "One-off" not in dishes_of(client)
    full = client.post("/api/food/entries", json={"day": DAY, "meal": "snack", "name": "Protein bar", "kcal": 200, "protein_g": 20, "carbs_g": 18, "fat_g": 7}, headers=MUTATE).json()
    assert full["carbs_g"] == 18 and full["fat_g"] == 7 and dishes_of(client)["Protein bar"]["fat_g"] == 7


def test_a_label_dish_carries_micros_and_logs_by_grams(fenv):  # noqa: F811
    client, _ = fenv
    made = client.post("/api/food/dishes", json={"name": "Granola", "unit": "1 serving (≈40 g)", "kcal": 180, "protein_g": 4, "carbs_g": 26, "fat_g": 6,
                                                  "grams": 40, "basis": "label", "note": "From a product label.",
                                                  "micros_per_100g": {"fibre_g": 7.5, "sodium_mg": 120, "bogus": 5}}, headers=MUTATE)
    assert made.status_code == 200
    dish = made.json()
    assert dish["basis"] == "label" and dish["micros_per_100g"] == {"fibre_g": 7.5, "sodium_mg": 120.0} and dish["per_100g"]["kcal"] == 450
    e = client.post("/api/food/entries", json={"day": DAY, "meal": "breakfast", "dish_id": dish["id"], "grams": 60}, headers=MUTATE).json()
    assert e["kcal"] == 270 and e["micros"] == {"fibre_g": 4.5, "sodium_mg": 72.0}
    nogram = client.post("/api/food/dishes", json={"name": "Mystery bar", "unit": "1 bar", "kcal": 150, "protein_g": None, "carbs_g": None, "fat_g": None,
                                                    "micros_per_100g": {"fibre_g": 3}}, headers=MUTATE).json()
    assert nogram["protein_g"] is None and nogram["micros_per_100g"] is None  # per-100 g amounts need a serving weight to mean anything
