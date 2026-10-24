from datetime import timedelta

import numpy as np

from cadence_app.analytics import freshness as FR
from tests.test_notes import D0, EASY, HARD, act


def world(effect=0.004, n=40, seed=3, ef_effect=0.0):
    """Hard runs on varied form; quality = 0.9 + effect·form + noise. pmc is faked so form is known."""
    rng = np.random.default_rng(seed)
    acts, dec, pmc, eff = [], {}, {}, []
    for i in range(n):
        day = D0 + timedelta(days=5 * i)
        form = float(rng.normal(0, 8))
        pmc[day] = {"form": form, "fitness": 40.0 + i * 0.2}
        a = act(i + 1, day, HARD if i % 2 == 0 else EASY)
        acts.append(a)
        if i % 2 == 0:
            q = 0.9 + effect * form + rng.normal(0, 0.015)
            dec[a.id] = {"best": {"300": 4.0 * q}}
        else:
            eff.append({"id": a.id, "day": day, "ef": 1.0 + ef_effect * form + rng.normal(0, 0.01), "hr": 150, "rhr": 50.0})
    # a few easy-looking early analysed runs so the first hard ones have a reference
    return {"acts": acts, "dec": dec, "pmc_by_day": pmc, "eff": eff}


def test_it_finds_that_fresher_hard_sessions_are_better_when_they_are():
    r = FR.fit(world(effect=0.004, n=80))
    h = r["hard"]
    assert h["enough"] and h["helpful"] and h["significant"]
    assert 0.2 < h["per_point_pct"] < 0.6 and h["ci_per_point_pct"][0] > 0 and h["split"]["diff_pct"] > 0 and h["points"]
    p = FR.payoff(r, 6.0)
    assert p["gain_pct"] > 1.0 and p["ci_pct"][0] <= p["gain_pct"] <= p["ci_pct"][1]


def test_no_relationship_is_reported_as_unproven_not_as_a_benefit():
    h = FR.fit(world(effect=0.0, n=80, seed=5))["hard"]
    assert h["enough"] and not h["helpful"]
    assert FR.payoff({"hard": h}, 6.0) is None


def test_small_samples_make_no_claim():
    h = FR.fit(world(n=14))["hard"]
    assert not h["enough"] and "per10_pct" not in h
    assert FR.payoff({"hard": h}, 6.0) is None


def test_easy_run_efficiency_has_its_own_check():
    e = FR.fit(world(n=120, ef_effect=0.004, seed=2))["easy"]
    assert e["enough"] and e["helpful"] and e["per10_pct"] > 1
    assert not FR.fit(world(n=20))["easy"]["enough"]


def test_a_tiny_form_gain_is_not_worth_quoting():
    r = FR.fit(world(effect=0.004, n=80))
    assert FR.payoff(r, 0.2) is None and FR.payoff(r, -3.0) is None


def test_result_is_json_serialisable():
    import json

    from fastapi.encoders import jsonable_encoder

    json.dumps(jsonable_encoder(FR.fit(world(n=80))))
