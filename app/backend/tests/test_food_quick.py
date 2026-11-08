"""Quick food logging: batch + idempotency, soft delete, frecency, usuals, suggestions, barcode, energy, migration. Synthetic data only."""
import re
import sqlite3
from datetime import date, datetime, time, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from cadence_app import energy_store, food_quick, foodlog as F
from cadence_app.analytics import energy as E
from cadence_app.analytics import foodrank as R
from cadence_app.analytics import foodsuggest as S
from cadence_app.analytics import notes
from cadence_app.db import MIGRATIONS_DIR
from cadence_app.models import Base, FoodDish, FoodEntry
from tests.test_api import MUTATE
from tests.test_foodlog import fenv, dishes_of  # noqa: F401  (fixtures)

TODAY = date(2026, 10, 22)
NOW = datetime(2026, 10, 22, 9, 0)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def dish(s, name, kcal=100.0, protein=5.0, grams=100.0, spread=20, **kw):
    d = FoodDish(name=name, unit="1 piece", kcal=kcal, protein_g=protein, carbs_g=10, fat_g=2, spread_pct=spread, builtin=False, active=True,
                 source="mine", basis="estimate", created_at=NOW, unit_g=grams, kcal_100g=kcal / grams * 100, protein_100g=None if protein is None else protein / grams * 100,
                 carbs_100g=10 / grams * 100, fat_100g=2 / grams * 100, **kw)
    s.add(d)
    s.commit()
    return d


def log(s, d, day, meal="breakfast", servings=1.0, **kw):
    return F.log_dish(s, day, meal, d.id, servings, False, TODAY, NOW, **kw)


# ---- frecency ----


def test_frecency_half_life_and_boosts_hand_computed():
    logs = [{"dish_id": 1, "day": TODAY - timedelta(days=14), "meal": "lunch"}, {"dish_id": 1, "day": TODAY - timedelta(days=28), "meal": "lunch"},
            {"dish_id": 2, "day": TODAY, "meal": "lunch"}, {"dish_id": 2, "day": TODAY - timedelta(days=1), "meal": "lunch"}]
    f = R.frecency(logs, TODAY, meal="lunch", weekday=0)  # 2026-10-22 is a Thursday: weekday 0 matches nothing here
    d1 = 0.5 * 1.5 + 0.25 * 1.5
    d2 = 1.0 * 1.5 + 0.5 ** (1 / 14) * 1.5
    assert f[2] == pytest.approx(1.0) and f[1] == pytest.approx(d1 / d2)


def test_frecency_same_weekday_and_meal_boost_and_single_log_cap():
    mon = date(2026, 10, 19)
    logs = [{"dish_id": 1, "day": mon, "meal": "dinner"}, {"dish_id": 1, "day": mon - timedelta(days=7), "meal": "dinner"},
            {"dish_id": 2, "day": mon, "meal": "dinner"}, {"dish_id": 3, "day": mon, "meal": "breakfast"}, {"dish_id": 3, "day": mon - timedelta(days=7), "meal": "breakfast"}]
    f = R.frecency(logs, TODAY, meal="dinner", weekday=0)
    assert f[1] == 1.0 and f[3] < f[1]  # same meal + weekday beats a different meal at equal counts
    assert f[2] <= 0.2  # logged once: capped
    assert R.frecency([], TODAY) == {}


def test_meal_guess_boundaries():
    assert [R.meal_guess(m) for m in (0, 659, 660, 929, 930, 1109, 1110, 1439)] == ["breakfast", "breakfast", "lunch", "lunch", "snack", "snack", "dinner", "dinner"]


def test_usual_combos_cluster_min_days_and_median_servings():
    logs = []
    for i, servings in enumerate((2, 2, 3, 2)):  # four days of idli + sambar, idli sometimes 3
        day = TODAY - timedelta(days=i + 1)
        logs += [{"dish_id": 1, "day": day, "meal": "breakfast", "servings": servings}, {"dish_id": 2, "day": day, "meal": "breakfast", "servings": 1}]
    logs += [{"dish_id": 9, "day": TODAY - timedelta(days=5), "meal": "breakfast", "servings": 1}]  # a one-off: no cluster
    logs += [{"dish_id": 1, "day": TODAY - timedelta(days=2), "meal": "dinner", "servings": 5}]  # other slot ignored
    u = R.usual_combos(logs, TODAY, "breakfast")
    assert len(u) == 1 and u[0]["n_days"] == 4 and sorted(u[0]["dish_ids"]) == [1, 2] and u[0]["servings"][1] == 2 and u[0]["last_day"] == TODAY - timedelta(days=1)
    assert R.usual_combos(logs[:4], TODAY, "breakfast") == []  # two days: below the minimum of three


def test_usual_combos_weekday_bonus_ranks_matching_cluster_first():
    a = [{"dish_id": 1, "day": TODAY - timedelta(days=d), "meal": "lunch", "servings": 1} for d in (1, 2, 3)]  # recent
    b = [{"dish_id": 2, "day": TODAY - timedelta(days=d), "meal": "lunch", "servings": 1} for d in (4, 5, 6)]
    u0 = R.usual_combos(a + b, TODAY, "lunch", weekday=(TODAY - timedelta(days=5)).weekday())
    # base scores favour the recent cluster by ~0.5; the +0.3 bonus lands on cluster b only if it has that weekday
    plain = R.usual_combos(a + b, TODAY, "lunch", weekday=9)
    assert plain[0]["dish_ids"] == [1] and u0[1]["score"] - plain[1]["score"] == pytest.approx(0.3)


def test_portion_memory_streak_marks_a_habit_after_three_identical_logs():
    m = None
    for s in (2, 2, 2):
        m = R.next_memory(m, s, "piece", 80)
    assert m["streak"] == 3 and m["n"] == 3 and R.is_habit(m)
    m = R.next_memory(m, 1, "piece", 40)
    assert m["streak"] == 1 and not R.is_habit(m) and m["servings"] == 1


# ---- batch log, idempotency ----


def test_batch_writes_whole_meal_and_retry_returns_original_without_duplicates(fenv):  # noqa: F811
    client, _ = fenv
    d = dishes_of(client)
    body = {"day": "2026-10-22", "meal": "breakfast", "eaten_at": "08:10", "client_key": "k-1",
            "items": [{"dish_id": d["Upma"]["id"], "servings": 2, "unit": "katori"}, {"dish_id": d["Paneer"]["id"], "grams": 100},
                      {"name": "Office tea", "kcal": 60, "protein_g": None, "save_dish": True}]}
    first = client.post("/api/food/log", json=body, headers=MUTATE).json()
    assert first["replayed"] is False and len(first["entries"]) == 3 and [e["eaten_at"] for e in first["entries"]] == ["08:10"] * 3
    assert first["entries"][2]["protein_g"] is None and [x["name"] for x in first["saved_dishes"]] == ["Office tea"]
    again = client.post("/api/food/log", json=body, headers=MUTATE).json()
    assert again["replayed"] is True and [e["id"] for e in again["entries"]] == [e["id"] for e in first["entries"]]
    viaheader = {k: v for k, v in body.items() if k != "client_key"}
    h1 = client.post("/api/food/log", json=viaheader, headers={**MUTATE, "Idempotency-Key": "hdr-1"}).json()
    h2 = client.post("/api/food/log", json=viaheader, headers={**MUTATE, "Idempotency-Key": "hdr-1"}).json()
    assert h2["replayed"] and [e["id"] for e in h2["entries"]] == [e["id"] for e in h1["entries"]]
    assert len(client.get("/api/food?day=2026-10-22").json()["entries"]) == 6


def test_batch_is_all_or_nothing_and_names_the_failing_item(fenv):  # noqa: F811
    client, _ = fenv
    d = dishes_of(client)
    r = client.post("/api/food/log", json={"day": "2026-10-22", "meal": "lunch", "client_key": "bad", "items": [
        {"dish_id": d["Upma"]["id"]}, {"dish_id": 999999}]}, headers=MUTATE)
    assert r.status_code == 400 and r.json()["detail"].startswith("Item 2:")
    assert client.get("/api/food?day=2026-10-22").json()["entries"] == []
    assert client.post("/api/food/log", json={"day": "2026-10-23", "meal": "lunch", "items": [{"dish_id": d["Upma"]["id"]}]}, headers=MUTATE).status_code == 400  # future
    assert client.post("/api/food/log", json={"day": "2026-10-22", "meal": "lunch", "items": []}, headers=MUTATE).status_code == 422
    assert client.post("/api/food/log", json={"day": "2026-10-22", "meal": "lunch", "items": [{"dish_id": 1}] * 41}, headers=MUTATE).status_code == 422
    assert client.post("/api/food/log", json={"day": "2026-10-22", "meal": "lunch", "eaten_at": "25:00", "items": [{"dish_id": d["Upma"]["id"]}]}, headers=MUTATE).status_code == 400


def test_partial_batch_is_completed_not_repeated(db):
    a, b = dish(db, "A"), dish(db, "B")
    F.log_dish(db, TODAY, "lunch", a.id, 1, False, TODAY, NOW, client_key="p:0")  # an earlier attempt wrote item 0 only
    out = F.log_batch(db, TODAY, "lunch", [{"dish_id": a.id}, {"dish_id": b.id}], False, None, "p", None, TODAY, NOW)
    assert len(out["entries"]) == 2 and out["replayed"] is False
    assert db.scalar(select(FoodEntry.id).where(FoodEntry.client_key == "p:0")) is not None
    assert len(list(db.scalars(select(FoodEntry)))) == 2


def test_batch_with_the_same_dish_twice_keeps_one_portion_memory_row(db):
    a = dish(db, "A")
    F.log_batch(db, TODAY, "lunch", [{"dish_id": a.id, "servings": 2}, {"dish_id": a.id, "servings": 2}], False, None, None, None, TODAY, NOW)
    m = food_quick.memory(db)
    assert m[a.id]["servings"] == 2


def test_default_eaten_at_is_now_for_today_and_unknown_for_a_past_day(fenv):  # noqa: F811
    client, _ = fenv
    u = dishes_of(client)["Upma"]["id"]
    today = client.post("/api/food/entries", json={"day": "2026-10-22", "meal": "lunch", "dish_id": u}, headers=MUTATE).json()
    past = client.post("/api/food/entries", json={"day": "2026-10-20", "meal": "lunch", "dish_id": u}, headers=MUTATE).json()
    assert re.fullmatch(r"\d\d:\d\d", today["eaten_at"]) and past["eaten_at"] is None and today["eaten_at_est"] is False


# ---- soft delete, restore, bulk, copy ----


def test_soft_delete_restore_and_exclusion_from_totals_history_and_copy(fenv):  # noqa: F811
    client, _ = fenv
    u = dishes_of(client)["Upma"]["id"]
    e = client.post("/api/food/entries", json={"day": "2026-10-21", "meal": "lunch", "dish_id": u}, headers=MUTATE).json()
    assert client.delete(f"/api/food/entries/{e['id']}", headers=MUTATE).status_code == 200
    assert client.delete(f"/api/food/entries/{e['id']}", headers=MUTATE).status_code == 404  # already removed
    view = client.get("/api/food?day=2026-10-21").json()
    assert view["entries"] == [] and view["summary"]["logged"] is False and view["recent_dish_ids"] == []
    assert view["micros"] == []
    assert client.patch(f"/api/food/entries/{e['id']}", json={"servings": 2}, headers=MUTATE).status_code == 404
    assert client.post("/api/food/copy", json={"source": "2026-10-21", "target": "2026-10-22"}, headers=MUTATE).json()["copied"] == 0
    assert client.post("/api/food/meals", json={"name": "Gone", "entry_ids": [e["id"]]}, headers=MUTATE).status_code == 400
    back = client.post(f"/api/food/entries/{e['id']}/restore", headers=MUTATE).json()
    assert back["id"] == e["id"] and back["deleted_at"] is None
    assert client.get("/api/food?day=2026-10-21").json()["summary"]["logged"] is True
    assert client.post("/api/food/entries/99999/restore", headers=MUTATE).status_code == 404


def test_replay_of_a_removed_entry_never_logs_it_again(fenv):  # noqa: F811
    client, _ = fenv
    u = dishes_of(client)["Upma"]["id"]
    body = {"day": "2026-10-22", "meal": "lunch", "dish_id": u, "client_key": "once"}
    e = client.post("/api/food/entries", json=body, headers=MUTATE).json()
    client.delete(f"/api/food/entries/{e['id']}", headers=MUTATE)
    again = client.post("/api/food/entries", json=body, headers=MUTATE).json()
    assert again["replayed"] is True
    assert client.get("/api/food?day=2026-10-22").json()["entries"] == []


def test_purge_only_removes_entries_deleted_over_a_week_ago(db):
    a = dish(db, "A")
    old, recent, live = (log(db, a, TODAY - timedelta(days=i)) for i in (1, 2, 3))
    F.remove(db, old["id"], NOW - timedelta(days=8))
    F.remove(db, recent["id"], NOW - timedelta(days=2))
    assert F.purge_deleted(db, NOW) == 1
    assert {e.id for e in db.scalars(select(FoodEntry))} == {recent["id"], live["id"]}


def test_bulk_move_scale_delete_restore_and_all_or_nothing(fenv):  # noqa: F811
    client, _ = fenv
    d = dishes_of(client)
    mk = lambda n, meal="lunch": client.post("/api/food/entries", json={"day": "2026-10-21", "meal": meal, "dish_id": d[n]["id"]}, headers=MUTATE).json()  # noqa: E731
    a, b = mk("Upma"), mk("Paneer")
    moved = client.post("/api/food/entries/bulk", json={"ids": [a["id"], b["id"]], "action": "move", "meal": "dinner"}, headers=MUTATE).json()
    assert moved["affected"] == 2 and {e["meal"] for e in moved["entries"]} == {"dinner"}
    scaled = client.post("/api/food/entries/bulk", json={"ids": [a["id"]], "action": "scale", "scale": 1.5}, headers=MUTATE).json()["entries"][0]
    assert scaled["servings"] == 1.5 and abs(scaled["kcal"] - a["kcal"] * 1.5) <= 1
    r = client.post("/api/food/entries/bulk", json={"ids": [a["id"], 987654], "action": "delete"}, headers=MUTATE)
    assert r.status_code == 400 and client.get("/api/food?day=2026-10-21").json()["summary"]["entries"] == 2
    r = client.post("/api/food/entries/bulk", json={"ids": [a["id"], b["id"]], "action": "scale", "scale": 5}, headers=MUTATE)
    assert r.status_code == 200  # 1.5 x 5 = 7.5 servings: fine
    r = client.post("/api/food/entries/bulk", json={"ids": [b["id"], a["id"]], "action": "scale", "scale": 4}, headers=MUTATE)
    assert r.status_code == 400  # 7.5 x 4 = 30 servings exceeds the cap; b (5 x 4 = 20, fine on its own) must not change either
    assert sorted(e["servings"] for e in client.get("/api/food?day=2026-10-21").json()["entries"]) == [5, 7.5]
    deleted = client.post("/api/food/entries/bulk", json={"ids": [a["id"], b["id"]], "action": "delete"}, headers=MUTATE).json()
    assert deleted["affected"] == 2 and client.get("/api/food?day=2026-10-21").json()["entries"] == []
    assert client.post("/api/food/entries/bulk", json={"ids": [a["id"]], "action": "delete"}, headers=MUTATE).status_code == 400  # already removed
    client.post("/api/food/entries/bulk", json={"ids": [a["id"], b["id"]], "action": "restore"}, headers=MUTATE)
    assert len(client.get("/api/food?day=2026-10-21").json()["entries"]) == 2
    assert client.patch("/api/food/entries/bulk", json={"servings": 2}, headers=MUTATE).status_code in (404, 405, 422)


def test_extended_copy_by_meal_entry_ids_and_target_meal(fenv):  # noqa: F811
    client, _ = fenv
    d = dishes_of(client)
    mk = lambda n, meal: client.post("/api/food/entries", json={"day": "2026-10-21", "meal": meal, "dish_id": d[n]["id"]}, headers=MUTATE).json()  # noqa: E731
    lunch, dinner = mk("Upma", "lunch"), mk("Paneer", "dinner")
    r = client.post("/api/food/copy", json={"source": "2026-10-21", "target": "2026-10-22", "meal": "lunch", "target_meal": "breakfast"}, headers=MUTATE).json()
    assert r["copied"] == 1 and r["entries"][0]["meal"] == "breakfast" and r["entries"][0]["source"] == "copy" and r["entries"][0]["name"] == "Upma"
    r = client.post("/api/food/copy", json={"source": "2026-10-21", "target": "2026-10-22", "entry_ids": [dinner["id"]]}, headers=MUTATE).json()
    assert r["copied"] == 1 and r["entries"][0]["meal"] == "dinner"
    assert client.post("/api/food/copy", json={"source": "2026-10-21", "target": "2026-10-22", "entry_ids": [dinner["id"], 424242]}, headers=MUTATE).status_code == 400
    assert client.post("/api/food/copy", json={"source": "2026-10-21", "target": "2026-10-22", "entry_ids": [lunch["id"]], "meal": "dinner"}, headers=MUTATE).status_code == 400


def test_patch_entry_meal_time_and_grams(fenv):  # noqa: F811
    client, _ = fenv
    p = dishes_of(client)["Paneer"]["id"]
    e = client.post("/api/food/entries", json={"day": "2026-10-21", "meal": "lunch", "dish_id": p, "grams": 100}, headers=MUTATE).json()
    r = client.patch(f"/api/food/entries/{e['id']}", json={"meal": "dinner", "eaten_at": "19:45", "grams": 50}, headers=MUTATE).json()
    assert r["meal"] == "dinner" and r["eaten_at"] == "19:45" and r["grams"] == 50 and r["kcal"] == round(e["kcal"] / 2)
    assert client.patch(f"/api/food/entries/{e['id']}", json={"eaten_at": None}, headers=MUTATE).json()["eaten_at"] is None
    assert client.patch(f"/api/food/entries/{e['id']}", json={}, headers=MUTATE).status_code == 400
    assert client.patch(f"/api/food/entries/{e['id']}", json={"servings": 1, "grams": 10}, headers=MUTATE).status_code == 400


# ---- chips, memory, pin, saved meals ----


def test_quick_chips_usual_yesterday_last_and_pinned_and_memory(fenv):  # noqa: F811
    client, _ = fenv
    d = dishes_of(client)
    for i in range(1, 5):
        client.post("/api/food/log", json={"day": f"2026-10-{22 - i}", "meal": "breakfast", "client_key": f"u{i}", "items": [
            {"dish_id": d["Upma"]["id"], "servings": 2}, {"dish_id": d["Paneer"]["id"], "servings": 1}]}, headers=MUTATE)
    client.patch(f"/api/food/dishes/{d['Paneer']['id']}", json={"pinned": True}, headers=MUTATE)
    q = client.get("/api/food/quick?day=2026-10-22&meal=breakfast").json()
    kinds = [c["kind"] for c in q["chips"]]
    assert kinds[:2] == ["usual", "yesterday"] and "pinned" in kinds and "last" in kinds and len(q["chips"]) <= 6
    usual = q["chips"][0]
    assert usual["n_days"] == 4 and {i["name"]: i["servings"] for i in usual["items"]} == {"Upma": 2, "Paneer": 1}
    k = usual["kcal"]
    assert k["low"] < k["value"] < k["high"] and k["value"] == sum(i["kcal"] for i in usual["items"])
    assert q["pinned"] == [d["Paneer"]["id"]] and q["memory"][str(d["Upma"]["id"])]["servings"] == 2 and q["memory"][str(d["Upma"]["id"])]["habitual"] is True
    assert re.fullmatch(r"breakfast|lunch|snack|dinner", q["meal_guess"])
    client.delete("/api/food/portion-memory", headers=MUTATE)
    assert client.get("/api/food/quick?day=2026-10-22&meal=breakfast").json()["memory"] == {}


def test_quick_chips_empty_history_is_empty_not_an_error(fenv):  # noqa: F811
    client, _ = fenv
    q = client.get("/api/food/quick").json()
    assert q["chips"] == [] and q["memory"] == {}


def test_saved_meal_pin_and_copy_excludes_removed(db):
    a, b = dish(db, "A"), dish(db, "B")
    e1, e2 = log(db, a, TODAY), log(db, b, TODAY)
    F.remove(db, e2["id"], NOW)
    with pytest.raises(F.FoodError):
        F.save_meal(db, "M", [e1["id"], e2["id"]], NOW)
    m = F.save_meal(db, "M", [e1["id"]], NOW)
    assert F.update_meal(db, m["id"], {"pinned": True})["pinned"] is True


# ---- barcode ----


def test_barcode_resolves_only_your_own_products_and_is_unique(fenv):  # noqa: F811
    client, _ = fenv
    assert client.get("/api/food/barcode/8901234567890").json() == {"found": False, "online_lookup": "off"}
    assert client.get("/api/food/barcode/12ab").status_code == 400
    mine = client.post("/api/food/dishes", json={"name": "Oat bar", "unit": "1 bar", "kcal": 180, "protein_g": 6, "basis": "label", "grams": 45,
                                                 "barcode": "890 1234-567890"}, headers=MUTATE).json()
    assert mine["barcode"] == "8901234567890" and mine["basis"] == "label"
    got = client.get("/api/food/barcode/8901234567890").json()
    assert got["found"] and got["dish"]["id"] == mine["id"]
    other = client.post("/api/food/dishes", json={"name": "Other bar", "unit": "1 bar", "kcal": 100}, headers=MUTATE).json()
    r = client.patch(f"/api/food/dishes/{other['id']}", json={"barcode": "8901234567890"}, headers=MUTATE)
    assert r.status_code == 400 and "Oat bar" in r.json()["detail"]
    assert client.patch(f"/api/food/dishes/{other['id']}", json={"barcode": "4006381333931"}, headers=MUTATE).json()["barcode"] == "4006381333931"
    assert client.patch(f"/api/food/dishes/{other['id']}", json={"barcode": None}, headers=MUTATE).json()["barcode"] is None
    assert client.patch(f"/api/food/dishes/{other['id']}", json={"barcode": "12"}, headers=MUTATE).status_code == 400
    assert client.get("/api/food/barcode/4006381333931").json()["found"] is False


# ---- suggestions ----


def cand(label="x", kcal=400, protein=20.0, micros=None, habit=0.5, times=3):
    return {"label": label, "source": "dish", "items": [], "kcal": kcal, "kcal_low": kcal * 0.8, "kcal_high": kcal * 1.2, "protein_g": protein,
            "micros": micros, "habit": habit, "times": times}


def run(cands, **kw):
    base = dict(candidates=cands, n_history=40, remaining_kcal=(1200.0, 1400.0), protein_gap_g=60.0, gaps=[], slots_left=3, day_logged=True)
    base.update(kw)
    return S.suggest(**base)


def test_suggest_needs_minimum_history_and_candidates():
    r = run([cand()], n_history=9)
    assert r["status"] == "insufficient" and r["suggestions"] == [] and "1 more" in r["needs"][0]
    assert run([cand()], n_history=10)["status"] == "ok"
    assert run([])["status"] == "insufficient"


def test_suggest_ranks_by_fit_and_formula_is_exact():
    r = run([cand("close", 433, 20.0), cand("far", 900, 20.0)])
    assert [s["label"] for s in r["suggestions"]] == ["close", "far"]
    budget, slot = 1300 / 3, 60 / 3
    expect = (0.35 * (1 - abs(433 - budget) / budget) + 0.30 * min(20 / slot, 1) + 0.20 * 0.5) / 0.85
    assert r["suggestions"][0]["score"] == pytest.approx(expect, abs=1e-3)
    assert r["suggestions"][0]["parts"]["fit_micro"] is None


def test_suggest_missing_inputs_drop_terms_instead_of_scoring_zero():
    none_at_all = run([cand(protein=None)], remaining_kcal=None, protein_gap_g=None)["suggestions"][0]
    assert none_at_all["parts"]["fit_kcal"] is None and none_at_all["parts"]["fit_prot"] is None and none_at_all["score"] == 0.5  # habit only
    unknown_protein = run([cand("u", 433, None), cand("k", 433, 20.0)])["suggestions"]
    assert unknown_protein[0]["label"] == "k" and unknown_protein[1]["parts"]["fit_prot"] == 0.0 and unknown_protein[1]["facts"]["day_logged"] is True
    assert any("isn't known" in x for x in notes.food_suggestion_reasons(unknown_protein[1]))
    over = run([cand()], remaining_kcal=(0.0, 0.0))["suggestions"][0]
    assert over["parts"]["fit_kcal"] is None  # nothing left: no kcal fit either way


def test_suggest_micronutrient_gaps_need_three_logged_days_and_known_values():
    rows = [{"key": "fibre_g", "label": "Fibre", "unit": "g", "amount": 5.0, "reference": 25, "kind": "target"},
            {"key": "sodium_mg", "label": "Sodium", "unit": "mg", "amount": 100.0, "reference": 2000, "kind": "limit"},
            {"key": "iron_mg", "label": "Iron", "unit": "mg", "amount": None, "reference": 18, "kind": "target"}]
    assert S.micro_gaps(rows, 2) == []
    g = S.micro_gaps(rows, 3)
    assert [x["key"] for x in g] == ["fibre_g"]  # limit and unreported nutrients are never gaps
    r = run([cand("fibre", micros={"fibre_g": 8.0}), cand("none", micros=None)], gaps=g)["suggestions"]
    assert r[0]["label"] == "fibre" and r[0]["parts"]["fit_micro"] == 1.0 and r[1]["parts"]["fit_micro"] is None
    assert r[0]["facts"]["micro_hits"][0]["pct_of_reference"] == 32


def test_suggest_is_deterministic_and_ties_break_by_label():
    a = run([cand("b"), cand("a")])
    assert [s["label"] for s in a["suggestions"]] == ["a", "b"] and a == run([cand("b"), cand("a")])


FORBIDDEN = re.compile(r"\bcaus(e|es|ed|ing)\b|because of|\bproves?\b|diagnos|\bhealthy\b|\bunhealthy\b|\bgood\b|\bbad\b|\bclean\b|cheat|guilt|burn (it )?off|"
                       r"\bshould\b|\bmust\b|junk|\bdeficien|lose weight|weight loss|\bfat loss\b|\blight\b|\bheavy\b|\bskip|\bavoid|you should take|\byou (have|are)\b|will improve|\bearn", re.I)


def test_every_suggestion_sentence_passes_the_forbidden_word_scan():
    facts = {"budget_kcal": 430, "remaining_kcal": 1300, "protein_gap_g": 60, "micro_hits": [{"label": "Fibre", "unit": "g", "amount": 8.0, "pct_of_reference": 32}],
             "day_logged": True, "protein_unknown": False, "times": 6}
    parts = {"fit_kcal": 0.9, "fit_prot": 0.5, "fit_micro": 1.0, "habit": 0.4}
    texts = []
    for logged in (True, False):
        for unknown in (True, False):
            texts += notes.food_suggestion_reasons({**cand(), "kcal_low": 350, "kcal_high": 520, "facts": {**facts, "day_logged": logged, "protein_unknown": unknown}, "parts": parts})
    texts += [notes.FOOD_SUGGEST_CAVEAT, notes.FOOD_SUGGEST_EMPTY]
    assert texts and not [t for t in texts if FORBIDDEN.search(t)]
    assert FORBIDDEN.search("this causes it") and FORBIDDEN.search("a healthy choice") and not FORBIDDEN.search("an estimate from your own log")


def test_suggest_endpoint_insufficient_then_ok_without_left_wording_on_an_empty_day(fenv):  # noqa: F811
    client, _ = fenv
    d = dishes_of(client)
    r = client.get("/api/food/suggest?day=2026-10-22&meal=lunch").json()
    assert r["status"] == "insufficient" and r["suggestions"] == [] and r["reasons_note"] == notes.FOOD_SUGGEST_EMPTY
    for i in range(1, 8):
        client.post("/api/food/log", json={"day": f"2026-10-{22 - i:02d}", "meal": "lunch", "client_key": f"s{i}", "items": [
            {"dish_id": d["Upma"]["id"], "servings": 1}, {"dish_id": d["Paneer"]["id"], "servings": 1}]}, headers=MUTATE)
    r = client.get("/api/food/suggest?day=2026-10-22&meal=lunch").json()
    assert r["status"] == "ok" and r["reasons_note"] == notes.FOOD_SUGGEST_CAVEAT and 1 <= len(r["suggestions"]) <= 3
    assert all(not FORBIDDEN.search(t) for s in r["suggestions"] for t in s["reasons"])
    assert not any("is left" in t for s in r["suggestions"] for t in s["reasons"])  # nothing logged today and no target: no 'left' wording
    assert r["suggestions"][0]["kcal"]["low"] < r["suggestions"][0]["kcal"]["high"]


# ---- energy: eaten so far ----


def entry(kcal, at=None, est=False):
    return {"kcal": kcal, "protein_g": 5, "carbs_g": None, "fat_g": None, "spread_pct": 20, "eaten_at": at, "eaten_at_est": est}


def test_energy_split_counts_only_entries_eaten_up_to_now():
    counted, later = E.split_eaten([entry(300, "08:00"), entry(500, "13:00"), entry(700, "20:30"), entry(100, None), entry(200, "21:00", est=True)], 14 * 60)
    assert [e["kcal"] for e in counted] == [300, 500, 100, 200] and [e["kcal"] for e in later] == [700]
    assert E.split_eaten([entry(1, "23:00")], None) == ([entry(1, "23:00")], [])
    assert E.later_summary([]) is None and E.later_summary(later) == {"entries": 1, "kcal": 700}


def test_energy_block_is_backward_compatible_and_reports_later_only_when_present():
    base = dict(today=TODAY, now_min=14 * 60, burn={"total": 1500.0, "active": 400.0, "as_of_min": 14 * 60}, finals={}, snapshots={}, workouts=[], settings=None)
    plain = E.assemble(food={TODAY: F.day_summary([entry(800)])}, **base)
    assert "later" not in plain["eaten"] and plain["eaten"]["kcal"] == 800
    s = {**F.day_summary([entry(800)]), "later": E.later_summary([entry(700, "20:30")])}
    assert E.assemble(food={TODAY: s}, **base)["eaten"]["later"] == {"entries": 1, "kcal": 700}
    only_later = E.assemble(food={TODAY: {**F.day_summary([]), "later": {"entries": 1, "kcal": 700}}}, **base)["eaten"]
    assert only_later["logged"] is False and only_later["kcal"] is None  # nothing eaten yet is not zero


def test_energy_loader_skips_removed_entries_and_future_times(db):
    a = dish(db, "A")
    morning = log(db, a, TODAY, eaten_at=time(8, 0))
    evening = log(db, a, TODAY, "dinner", eaten_at=time(20, 0))
    gone = log(db, a, TODAY, eaten_at=time(9, 0))
    old = log(db, a, TODAY - timedelta(days=1), "dinner", eaten_at=time(22, 0))  # a past day is never cut by the clock
    F.remove(db, gone["id"], NOW)
    out = energy_store._food_by_day(db, TODAY - timedelta(days=3), TODAY, None, 12 * 60)  # noqa: SLF001
    assert out[TODAY]["entries"] == 1 and out[TODAY]["kcal"] == morning["kcal"] and out[TODAY]["later"] == {"entries": 1, "kcal": evening["kcal"]}
    assert out[TODAY - timedelta(days=1)]["kcal"] == old["kcal"] and out[TODAY - timedelta(days=1)]["later"] is None
    allday = energy_store._food_by_day(db, TODAY, TODAY, None, None)  # noqa: SLF001
    assert allday[TODAY]["entries"] == 2


# ---- migration ----


def _config(db):
    c = Config()
    c.set_main_option("script_location", str(MIGRATIONS_DIR))
    c.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    return c


def test_migration_0032_up_backfills_and_down_keeps_rows_without_cascades(tmp_path):
    db = tmp_path / "m.sqlite3"
    cfg = _config(db)
    command.upgrade(cfg, "0031")
    con = sqlite3.connect(db)
    con.execute("INSERT INTO food_dishes (id, name, unit, kcal, spread_pct, builtin, active, source, basis, flagged, edited, created_at) VALUES (1,'D','1',100,20,0,1,'mine','estimate',0,0,'2026-10-01')")
    for i, meal in enumerate(("breakfast", "lunch", "snack", "dinner")):
        con.execute("INSERT INTO food_entries (id, day, meal, dish_id, name, servings, kcal, spread_pct, logged_at) VALUES (?, '2026-10-20', ?, 1, 'D', 1, 100, 20, '2026-10-20 07:00:00')", (i + 1, meal))
    con.commit()
    con.close()
    command.upgrade(cfg, "head")
    con = sqlite3.connect(db)
    rows = con.execute("SELECT meal, eaten_at, eaten_at_est, deleted_at, source FROM food_entries ORDER BY id").fetchall()
    assert rows == [("breakfast", "08:00:00", 1, None, "manual"), ("lunch", "13:00:00", 1, None, "manual"), ("snack", "16:30:00", 1, None, "manual"), ("dinner", "20:00:00", 1, None, "manual")]
    assert con.execute("SELECT pinned, barcode FROM food_dishes").fetchall() == [(0, None)]
    con.execute("INSERT INTO food_portion_memory (dish_id, servings, updated_at) VALUES (1, 2, '2026-10-20')")
    con.execute("UPDATE food_entries SET deleted_at = '2026-10-21 00:00:00' WHERE id = 4")
    con.execute("UPDATE food_dishes SET barcode = '8901234567890'")
    with pytest.raises(sqlite3.IntegrityError):  # the unique index on a set barcode
        con.execute("INSERT INTO food_dishes (name, unit, kcal, spread_pct, builtin, active, source, basis, flagged, edited, created_at, barcode) VALUES ('E','1',1,20,0,1,'mine','estimate',0,0,'2026-10-01','8901234567890')")
    con.commit()
    con.close()
    command.downgrade(cfg, "0031")
    con = sqlite3.connect(db)
    cols = {r[1] for r in con.execute("PRAGMA table_info(food_entries)")}
    assert not cols & {"eaten_at", "eaten_at_est", "deleted_at", "source"} and "client_key" in cols
    assert {r[1] for r in con.execute("PRAGMA table_info(food_dishes)")} & {"barcode", "pinned"} == set()
    assert con.execute("SELECT id FROM food_entries ORDER BY id").fetchall() == [(1,), (2,), (3,)]  # the removed one is not resurrected; none cascaded away
    assert con.execute("SELECT count(*) FROM food_dishes").fetchone() == (1,)
    assert con.execute("SELECT count(*) FROM sqlite_master WHERE name = 'food_portion_memory'").fetchone() == (0,)
    con.close()
    command.upgrade(cfg, "head")  # and up again


def test_only_the_known_places_select_entries_without_the_removed_filter():
    """Every other read goes through foodlog.active_entries(); a new raw select must be added here on purpose."""
    from pathlib import Path
    import cadence_app
    raw = []
    for p in Path(cadence_app.__file__).parent.glob("*.py"):
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if re.search(r"select\(FoodEntry\)|select_from\(FoodEntry\)", line) and "deleted_at" not in line and "active_entries" not in line:
                raw.append((p.name, line.strip()[:70]))
    allowed = {"foodlog.py": 4, "food_quick.py": 1}  # foodlog: client_key lookups (a replay finds removed rows on purpose) and bulk by id (restore needs them); food_quick: a count whose next line filters deleted_at
    found = {}
    for name, _ in raw:
        found[name] = found.get(name, 0) + 1
    assert found == allowed, raw
