from datetime import date, timedelta

import numpy as np

from cadence_app.analytics import banister as B

D0 = date(2025, 1, 6)


def history(days=330, seed=3, tau=(24, 12), k=(0.03, 0.05), noise=0.5, signal=True):
    """Block-periodised synthetic load, and weekly performance generated from a known impulse-response model."""
    rng = np.random.default_rng(seed)
    load = {}
    for i in range(days):
        block = (i // 21) % 3  # build, build, recovery
        base = (0, 70, 0, 90, 60, 100, 0)[i % 7] * (0.4 if block == 2 else 1.0 + 0.3 * block)
        if base:
            load[D0 + timedelta(days=i)] = float(base * rng.uniform(0.8, 1.2))
    w = np.zeros(days)
    for d, x in load.items():
        w[(d - D0).days] = x
    e1, e2 = B._impulse(w, tau[0]), B._impulse(w, tau[1])
    obs = []
    for i in range(10, days, 7):
        v = 10 + (k[0] * e1[i] - k[1] * e2[i] if signal else 0) + rng.normal(0, noise)
        obs.append((D0 + timedelta(days=i), float(v)))
    return load, obs, D0 + timedelta(days=days - 1)


def test_recovers_the_time_constants_it_was_generated_with():
    load, obs, end = history()
    r = B.fit(load, obs, end)
    assert r["valid"] and r["adopted"], r.get("why_not")
    assert abs(r["tau1"] - 24) <= 6 and abs(r["tau2"] - 12) <= 3 and not r["consistent_with_default"]
    lo, hi = r["region"]["tau1"]
    assert lo <= 24 <= hi and r["cv"]["gain_vs_default_pct"] > 0 and r["r2"] > 0.5
    assert len(r["series"]) == len(obs) and "_model" in r and "_model" not in B.public(r)


def test_data_that_match_the_standard_constants_do_not_adopt_a_personal_pair():
    load, obs, end = history(tau=(42, 7), k=(0.02, 0.06), seed=5)
    r = B.fit(load, obs, end)
    assert r["valid"] and not r["adopted"] and r["consistent_with_default"]


def test_pure_noise_is_not_adopted():
    load, obs, end = history(signal=False, noise=1.0, seed=7)
    r = B.fit(load, obs, end)
    assert r["valid"] and not r["adopted"] and r["why_not"]


def test_too_little_data_says_what_is_missing():
    load, obs, end = history(days=120)
    r = B.fit(load, obs[:8], end)
    assert not r["valid"] and "weeks of runs" in r["missing"]


def test_curve_follows_the_load_and_taper_is_reported():
    load, obs, end = history()
    r = B.fit(load, obs, end)
    base = {p["day"]: p["value"] for p in B.curve(r, load, end, step=1, since=end - timedelta(days=30))}
    rested = {d: 0.0 if d > end - timedelta(days=10) else x for d, x in load.items()}
    after = {p["day"]: p["value"] for p in B.curve(r, rested, end, step=1, since=end - timedelta(days=30))}
    assert after[end] != base[end]
    assert r["taper"] is None or r["taper"]["range"][0] <= r["taper"]["range"][1]


def test_weekly_series_takes_the_median_per_week():
    pts = [{"day": D0 + timedelta(days=i), "ef": v} for i, v in ((0, 1.0), (1, 3.0), (2, 2.0), (8, 5.0))]
    out = B.weekly_series(pts)
    assert out == [(D0 + timedelta(days=3), 2.0), (D0 + timedelta(days=10), 5.0)]


def test_result_is_json_serialisable():
    import json

    from fastapi.encoders import jsonable_encoder

    load, obs, end = history()
    r = B.fit(load, obs, end)
    out = B.public(r)
    out["curve"] = B.curve(r, load, end, step=3, since=obs[0][0])
    json.dumps(jsonable_encoder(out))


def saturating_history(alpha=0.6, seed=11):
    """Performance responds to load**alpha, so big days buy proportionally less."""
    rng = np.random.default_rng(seed)
    load, _, end = history()
    eff = B.effective(load, alpha)
    w = np.zeros((end - D0).days + 1)
    for d, x in eff.items():
        w[(d - D0).days] = x
    e1, e2 = B._impulse(w, 42), B._impulse(w, 7)
    obs = [(D0 + timedelta(days=i), float(10 + 0.03 * e1[i] - 0.09 * e2[i] + rng.normal(0, 0.25))) for i in range(10, len(w), 7)]
    return load, obs, end


def test_effective_load_flattens_big_days_and_keeps_typical_ones():
    out = B.effective({D0: 50.0, D0 + timedelta(days=1): 100.0, D0 + timedelta(days=2): 0.0, D0 + timedelta(days=3): 150.0}, 0.6)
    assert out[D0 + timedelta(days=2)] == 0.0
    assert out[D0 + timedelta(days=3)] / out[D0 + timedelta(days=1)] < 1.5  # 1.5× the load is less than 1.5× the effect
    assert B.effective({D0: 50.0}, 1.0) == {D0: 50.0}
    assert B.effective({}, 0.6) == {}


def test_saturation_is_adopted_only_when_the_data_call_for_it():
    load, obs, end = saturating_history()
    s = B.saturation(load, obs, end)
    assert s["valid"] and s["adopted"] and s["alpha"] < 1.0 and s["gain_pct"] >= 5
    lin_load, lin_obs, lin_end = history(tau=(42, 7), k=(0.02, 0.06), seed=5)
    flat = B.saturation(lin_load, lin_obs, lin_end)
    assert flat["valid"] and not flat["adopted"] and flat["alpha"] == 1.0
    assert not B.saturation(lin_load, lin_obs[:6], lin_end)["valid"]


def test_the_fit_keeps_the_plausible_constant_pairs():
    load, obs, end = history()
    r = B.fit(load, obs, end)
    assert 1 <= len(r["region_pairs"]) <= 30 and all(a >= 2 * b for a, b in r["region_pairs"])
