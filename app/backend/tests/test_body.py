from datetime import date

from cadence_app.analytics import body
from tests.test_api import env  # noqa: F401  (fixture)

MALE_30 = {"height_cm": 175.0, "birth_date": date(1996, 10, 24), "sex": "male"}
FEMALE_30 = {"height_cm": 165.0, "birth_date": date(1996, 10, 24), "sex": "female"}


def test_bmi_category_thresholds():
    assert body.bmi_category(18.4) == "underweight"
    assert body.bmi_category(18.5) == "normal" and body.bmi_category(24.9) == "normal"
    assert body.bmi_category(25.0) == "overweight" and body.bmi_category(29.9) == "overweight"
    assert body.bmi_category(30.0) == "obese"


def test_estimate_matches_hand_computed_reference_values():
    e = body.estimate(70.0, MALE_30, date(2026, 10, 24))
    assert e is not None
    assert e.bmi == 22.9 and e.bmi_category == "normal"
    assert e.body_fat_pct == 18.1
    assert e.fat_mass_kg == 12.7 and e.lean_mass_kg == 57.3
    assert e.fat_mass_kg + e.lean_mass_kg == 70.0  # mass conserved
    assert e.bmr_kcal == 1649


def test_sex_changes_both_formulas_in_the_expected_direction():
    male = body.estimate(70.0, MALE_30, date(2026, 10, 24))
    female = body.estimate(70.0, {**MALE_30, "sex": "female"}, date(2026, 10, 24))
    assert female.body_fat_pct > male.body_fat_pct  # Deurenberg's -10.8*sex term
    assert female.bmr_kcal < male.bmr_kcal  # the +5 vs -161 constant


def test_older_age_raises_the_body_fat_estimate_at_the_same_weight_and_height():
    younger = body.estimate(70.0, MALE_30, date(2016, 10, 24))  # age ~20
    older = body.estimate(70.0, MALE_30, date(2046, 10, 24))  # age ~50
    assert older.body_fat_pct > younger.body_fat_pct


def test_estimate_is_none_outside_a_sane_range():
    assert body.estimate(5.0, MALE_30, date(2026, 10, 24)) is None  # implausible weight
    assert body.estimate(70.0, {**MALE_30, "height_cm": 400.0}, date(2026, 10, 24)) is None


def test_body_fat_percent_is_clamped_to_a_physiologically_sane_range():
    # A very low BMI/age combination shouldn't produce a negative or implausible body-fat estimate.
    tiny = body.estimate(42.0, {**FEMALE_30, "height_cm": 160.0, "birth_date": date(2008, 10, 24)}, date(2026, 10, 24))
    assert tiny is not None and 2.0 <= tiny.body_fat_pct <= 70.0


def test_weight_endpoint_includes_body_estimates_once_a_profile_is_set(env):  # noqa: F811
    from tests.test_api import MUTATE

    client, _ = env
    client.post("/api/sync/demo", headers=MUTATE)
    assert client.get("/api/settings/profile").json() == {"profile": None}
    before = client.get("/api/weight?days=30").json()
    assert before["body_profile"] is None and all(p["body"] is None for p in before["points"])

    too_tall = client.put("/api/settings/profile", json={"height_cm": 400, "birth_date": "1990-01-01", "sex": "male"}, headers=MUTATE)
    assert too_tall.status_code == 422  # rejected by the request schema before it reaches profile.save()
    future_birth = client.put("/api/settings/profile", json={"height_cm": 178.0, "birth_date": "2999-01-01", "sex": "male"}, headers=MUTATE)
    assert future_birth.status_code == 400  # schema-valid but rejected by profile.save()'s own check

    r = client.put("/api/settings/profile", json={"height_cm": 178.0, "birth_date": "1990-01-01", "sex": "male"}, headers=MUTATE)
    assert r.status_code == 200 and r.json()["profile"]["height_cm"] == 178.0

    after = client.get("/api/weight?days=30").json()
    assert after["body_profile"]["height_cm"] == 178.0
    points_with_body = [p for p in after["points"] if p["body"] is not None]
    assert points_with_body and all(0 < p["body"]["bmi"] < 60 for p in points_with_body)
    assert points_with_body[-1]["body"]["bmi_category"] in ("underweight", "normal", "overweight", "obese")
