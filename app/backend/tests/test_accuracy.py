from datetime import date, timedelta

import pytest

from cadence_app.analytics import accuracy as AC
from cadence_app.analytics import planner as PL
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)
from tests.test_planner import training_ctx


def plan(i, ratio, sport="run", predicted=100.0, status="done"):
    return {"id": i, "day": date(2026, 5, 1) + timedelta(days=i), "sport": sport, "kind": "easy", "title": "t", "status": status,
            "predicted": {"load": predicted * 1.5, "load_raw": predicted, "load_range": [80, 120]},
            "activity": {"load": predicted * ratio} if status == "done" else None}


def test_summarise_needs_enough_sessions():
    assert AC.summarise([{"predicted": 100, "actual": 90}] * 4) == {"n": 4, "enough": False}


def test_consistent_underprediction_is_called_a_bias_and_corrected_with_shrinkage():
    noise = [0.97, 1.03, 1.0, 1.05, 0.95, 1.02, 0.98, 1.04, 0.96, 1.01, 1.0, 0.99]
    scored = AC.score_plans([plan(i, 1.3 * n) for i, n in enumerate(noise)])
    o = scored["overall"]
    assert o["n"] == 12 and o["biased"] and o["bias_pct"] == pytest.approx(30, abs=3) and o["ratio_ci"][0] > 1.2
    cal = AC.calibration(scored)
    assert 1.1 < cal["run"]["factor"] < 1.3  # shrunk towards 1, never the full 1.3
    assert cal["all"]["n"] == 12


def test_noise_around_the_truth_is_not_a_bias():
    ratios = [0.7, 1.4, 0.9, 1.2, 0.8, 1.3, 1.0, 1.1, 0.75, 1.35, 0.95, 1.05]
    scored = AC.score_plans([plan(i, r) for i, r in enumerate(ratios)])
    assert not scored["overall"]["biased"] and AC.calibration(scored) == {}
    assert scored["overall"]["typical_error_pct"] > 5


def test_small_samples_never_correct():
    scored = AC.score_plans([plan(i, 1.5) for i in range(7)])
    assert scored["overall"]["enough"] and not scored["overall"]["biased"] and AC.calibration(scored) == {}


def test_scoring_uses_the_uncorrected_prediction_and_counts_missed_plans():
    plans = [plan(i, 1.0) for i in range(6)] + [plan(10, 1.0, status="missed")]
    scored = AC.score_plans(plans)
    assert scored["overall"]["bias_pct"] == 0 and scored["followed"] == {"done": 6, "missed": 1, "of": 7}
    assert scored["overall"]["range_coverage_pct"] == 100


def test_planner_applies_a_calibration_and_says_so():
    c = training_ctx()
    model = PL.load_model(c["acts"], c["as_of"])
    day = c["as_of"] + timedelta(days=1)
    option = next(o for o in PL.run_options(c, None) if o["kind"] == "easy")
    base = PL.predict(c, model, day, option, [])
    assert base["calibration"] is None and base["load_raw"] == base["load"]
    c["calibration"] = {"run": {"factor": 1.2, "n": 14}}
    fixed = PL.predict(c, model, day, option, [])
    assert fixed["load_raw"] == base["load"] and fixed["load"] == pytest.approx(base["load"] * 1.2, abs=1)
    assert fixed["calibration"] == {"factor": 1.2, "n": 14}


def test_backtest_on_a_regular_history_is_accurate():
    c = training_ctx()
    bt = AC.backtest(c)
    assert bt["enough"] and bt["n"] >= 20 and bt["typical_error_pct"] <= 15 and not bt["biased"]


def test_lab_endpoints_answer_even_without_enough_data(env):  # noqa: F811
    client, _ = env
    assert client.get("/api/lab/accuracy").json() == {"has_data": False}
    client.post("/api/sync/demo", headers=MUTATE)
    acc = client.get("/api/lab/accuracy").json()
    assert acc["has_data"] and acc["headline"]["text"] and acc["plans"]["overall"]["n"] == 0 and "rows" not in acc["plans"]
    model = client.get("/api/lab/model").json()
    assert model["has_data"] and model["headline"]["text"] and "_model" not in model
    routes = client.get("/api/lab/routes").json()
    assert routes["has_data"] and routes["routes"] == [] and routes["reason"]
    wi = client.get("/api/lab/whatif").json()
    assert wi["has_data"] and set(wi["actions"]) == {"skip", "easy", "half"}
    assert client.get("/api/lab/whatif/replay?edit=abc").status_code == 400
    assert client.get("/api/lab/whatif/replay?edit=1:nope").status_code == 400
    recent = wi["recent"]
    if recent:
        r = client.get(f"/api/lab/whatif/replay?edit={recent[0]['id']}:skip")
        assert r.status_code == 200 and r.json()["headline"] and r.json()["trajectory"]


def test_a_realised_plan_is_scored_and_stored_predictions_keep_the_raw_load(env):  # noqa: F811
    client, clock = env
    client.post("/api/sync/demo", headers=MUTATE)
    today = clock.today()
    opts = client.get(f"/api/planner/options?day={today}&sport=run").json()["options"]
    made = client.post("/api/planner", json={"day": str(today), "sport": "run", "option_key": opts[0]["key"]}, headers=MUTATE).json()
    assert made["predicted"]["load_raw"] == made["predicted"]["load"] and made["predicted"]["calibration"] is None
    acc = client.get("/api/lab/accuracy").json()
    assert acc["calibration"] == {} and acc["plans"]["followed"] is None or acc["plans"]["followed"]["of"] >= 0
