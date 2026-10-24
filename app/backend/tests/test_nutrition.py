from datetime import date, timedelta

from cadence_app.analytics import nutrition as N
from cadence_app.analytics import notes as coach_notes
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)

T = date(2026, 10, 22)


def logged(day, kcal, protein=None, spread=0.2):
    return {"day": day, "logged": True, "entries": 1, "kcal": kcal, "kcal_low": round(kcal * (1 - spread)), "kcal_high": round(kcal * (1 + spread)),
            "protein_g": protein, "carbs_g": None, "fat_g": None, "protein_g_per_kg": None, "partial_macros": False}


def gap(day):
    return {"day": day, "logged": False, "entries": 0, "kcal": None, "kcal_low": None, "kcal_high": None, "protein_g": None,
            "carbs_g": None, "fat_g": None, "protein_g_per_kg": None, "partial_macros": False}


def test_phase_needs_a_real_difference_between_weight_and_goal():
    assert N.phase(80, 72) == "cut" and N.phase(70, 74) == "gain"
    assert N.phase(80, 80.3) == "maintain" and N.phase(None, 70) == "maintain" and N.phase(80, None) == "maintain"


def test_reference_energy_prefers_a_weeks_of_garmin_and_ignores_today():
    burn = {T - timedelta(days=i): 2600.0 + i for i in range(0, 12)}
    ref = N.reference_energy(burn, T, 2400)
    assert ref["source"] == "garmin" and ref["days"] == 11  # today (a partial day) is left out
    assert ref["low"] < ref["kcal"] < ref["high"]
    few = {T - timedelta(days=i): 2600.0 for i in range(1, 5)}
    assert N.reference_energy(few, T, 2400)["source"] == "formula"
    assert N.reference_energy(few, T, None) is None


def test_cut_target_follows_the_loss_rate_and_never_dips_below_resting_energy():
    ref = {"kcal": 2600}
    cut = N.targets("cut", 80, ref, bmr_kcal=1700)
    # 0.5% and 1% of 80 kg a week at 7,700 kcal/kg = 440 and 880 kcal/day; the firm end is capped at 25% (650)
    assert cut["kcal"] == [1950, 2160] and cut["pace_kg_week"] == [0.4, 0.8] and cut["protein_g"] == [128, 176]
    assert N.targets("cut", 80, {"kcal": 2000}, bmr_kcal=1900)["kcal"][0] == 1900
    gain = N.targets("gain", 70, ref, bmr_kcal=1700)
    assert gain["kcal"] == [2860, 3120] and gain["pace_pct_week"] == [0.25, 0.5]
    assert N.targets("maintain", 70, ref, bmr_kcal=1700)["kcal"] == [2470, 2730]
    assert N.targets("cut", 80, None, None)["kcal"] is None  # protein and fat still come from weight alone


def test_day_status_compares_ranges_so_an_uncertain_day_is_not_called_over():
    day = lambda k: logged(T, k)  # noqa: E731  (+-20%)
    assert N.day_status(gap(T), [1950, 2160]) == {"state": "not_logged"}
    assert N.day_status(day(2000), None)["state"] == "no_target"
    assert N.day_status(day(2300), [1950, 2160])["state"] == "within"  # 1840-2760 overlaps the target
    assert N.day_status(day(1200), [1950, 2160])["state"] == "under"  # 960-1440 sits entirely below
    assert N.day_status(day(3500), [1950, 2160])["state"] == "over"


def test_balance_needs_four_logged_days_with_a_garmin_figure():
    days = [T - timedelta(days=i) for i in range(6, 0, -1)]
    burn = {d: 2600.0 for d in days}
    trail = [logged(d, 2000) for d in days[:3]] + [gap(d) for d in days[3:]]
    assert N.balance(trail, burn) is None
    trail = [logged(d, 2000) for d in days[:5]] + [gap(days[5])]
    b = N.balance(trail, burn)
    assert b["days"] == 5 and b["intake"] == 2000 and b["burn"] == 2600 and b["balance"] == -600
    assert b["balance_range"][0] < -600 < b["balance_range"][1]
    assert N.balance(trail, {d: 2600.0 for d in days[:2]}) is None  # logged days without a burn figure don't count


def test_implied_expenditure_adds_back_the_energy_in_the_trend():
    trail = [logged(T - timedelta(days=i), 2000) for i in range(13, 3, -1)] + [gap(T - timedelta(days=i)) for i in range(3, 0, -1)]
    imp = N.implied_expenditure(trail, rate_kg_per_week=-0.5, rate_se_kg_per_week=0.1)
    assert imp["days"] == 10 and imp["kcal"] == round(2000 + 0.5 * 1100)  # losing 0.5 kg/week is a 550 kcal/day deficit
    assert imp["range"][0] < imp["kcal"] < imp["range"][1]
    assert N.implied_expenditure(trail[:9], -0.5, 0.1) is None and N.implied_expenditure(trail, None, None) is None


def test_protein_average_skips_days_without_protein_and_needs_four():
    trail = [logged(T - timedelta(days=i), 2000, protein=p) for i, p in enumerate([120, 140, None, 130, 150])]
    assert N.protein_average(trail, 80) == {"days": 4, "g": 135, "g_per_kg": 1.69}
    assert N.protein_average(trail[:3], 80) is None


def plan_for(**kw):
    days = [T - timedelta(days=i) for i in range(13, -1, -1)]
    burn = {d: 2600.0 for d in days}
    trail14 = [logged(d, kw.get("kcal", 2000), protein=kw.get("protein", 120)) for d in days]
    return N.food_plan(weight_kg=80, goal_kg=kw.get("goal", 74), today_summary=trail14[-1], trail=trail14[-7:], trail14=trail14, entries=[],
                       burn_by_day=burn, today=T, formula={"bmr": 1700, "active": 2400}, rate_kg_per_week=kw.get("rate", -0.5), rate_se_kg_per_week=0.1)


def test_notes_flag_low_protein_and_say_when_logs_and_weight_agree():
    plan = plan_for(protein=100, rate=-0.5)  # 100 g / 80 kg = 1.25 g/kg
    ids = {n["id"]: n for n in coach_notes.nutrition(plan)}
    assert ids["food_protein"]["severity"] == "warn" and "1.25 g/kg" in ids["food_protein"]["detail"]
    assert ids["food_implied"]["severity"] == "good"  # 2000 + 550 ~ 2550 vs 2600
    off = {n["id"]: n for n in coach_notes.nutrition(plan_for(rate=0.1))}
    assert off["food_implied"]["severity"] == "info" and "burn less" in off["food_implied"]["title"]


def test_the_page_says_what_it_needs_and_never_invents_targets(env):  # noqa: F811
    client, _ = env
    empty = client.get("/api/food").json()
    assert empty["plan"]["needs"] == ["weight", "profile"] and empty["plan"]["targets"] is None and empty["notes"] == []
    client.post("/api/weight/entries", json={"day": "2026-10-22", "weight_kg": 80}, headers=MUTATE)
    client.put("/api/settings/profile", json={"height_cm": 180, "birth_date": "1990-01-01", "sex": "male"}, headers=MUTATE)
    client.put("/api/settings/weight-goal", json={"goal_kg": 74}, headers=MUTATE)
    plan = client.get("/api/food").json()["plan"]
    assert plan["needs"] == [] and plan["phase"] == "cut" and plan["reference_energy"]["source"] == "formula"
    assert plan["targets"]["kcal"][0] < plan["targets"]["kcal"][1] and plan["targets"]["protein_g"] == [128, 176]
    assert plan["balance"] is None and plan["implied"] is None  # nothing logged yet: no averages


def test_the_data_note_says_what_is_actually_missing():
    no_burn = N.food_plan(weight_kg=80, goal_kg=74, today_summary=logged(T, 2000), trail=[logged(T - timedelta(days=i), 2000) for i in range(6, -1, -1)],
                          trail14=[], entries=[], burn_by_day={}, today=T, formula={"bmr": 1700, "active": 2400}, rate_kg_per_week=None, rate_se_kg_per_week=None)
    note = next(n for n in coach_notes.nutrition(no_burn) if n["id"] == "food_data")
    assert "7 logged days" in note["detail"] and "Garmin has not reported" in note["detail"]
    few = N.food_plan(weight_kg=80, goal_kg=74, today_summary=gap(T), trail=[logged(T - timedelta(days=i), 2000) for i in range(1, 3)] + [gap(T)],
                      trail14=[], entries=[], burn_by_day={}, today=T, formula=None, rate_kg_per_week=None, rate_se_kg_per_week=None)
    assert "Log a few more days" == next(n for n in coach_notes.nutrition(few) if n["id"] == "food_data")["title"]
