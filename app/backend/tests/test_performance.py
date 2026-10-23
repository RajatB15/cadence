from datetime import date, timedelta

import pytest

from cadence_app.analytics import performance as P

D0 = date(2026, 5, 1)


def stream(seconds: int, speed, hr=150.0, alt=None) -> dict:
    t = list(range(0, seconds, 3))
    sp = [speed(s) if callable(speed) else speed for s in t]
    out = {"t": t, "speed": sp, "heart_rate": [hr(s) if callable(hr) else hr for s in t]}
    if alt is not None:
        out["altitude"] = [alt(s) for s in t]
    return out


def test_grade_factor_follows_minetti_with_damped_downhill():
    assert P.grade_factor(0) == pytest.approx(1.0)
    assert P.grade_factor(0.10) == pytest.approx(1.66, abs=0.02)
    assert 0.75 < P.grade_factor(-0.10) < 1.0  # half of Minetti's downhill saving
    assert P.grade_factor(0.6) == P.grade_factor(0.25)


def test_grade_adjusted_speed_credits_climbs():
    climb = stream(1200, 2.5, alt=lambda s: s * 2.5 * 0.08)  # steady 8% climb
    gap = P.grade_adjusted(climb)
    assert gap[-1] > 2.5 * 1.4 and gap[0] == 2.5  # no grade evidence at the very start
    assert P.grade_adjusted(stream(600, 3.0)) == [3.0] * 200


def test_best_efforts_find_the_fast_block():
    s = stream(3600, lambda x: 5.0 if 1000 <= x < 1180 else 3.0)
    best = P.best_efforts(s["t"], s["speed"])
    assert best["180"] == pytest.approx(5.0, abs=0.05)
    assert 3.0 < best["1200"] < 3.4 and "1800" in best


def runs_from_curve(cs: float, d_prime: float) -> list[dict]:
    return [{"id": i, "day": D0 + timedelta(days=i), "name": "x",
             "best": {str(t): round(cs + d_prime / t, 3) for t in P.CS_DURATIONS if t % (i + 1) == 0 or i == 0}}
            for i in range(3)]


def test_critical_speed_recovers_known_curve_and_predicts():
    r = P.critical_speed(runs_from_curve(4.0, 200), D0 + timedelta(days=10))
    assert r["valid"] and r["cs_mps"] == pytest.approx(4.0, abs=0.02) and r["d_prime_m"] == pytest.approx(200, abs=10)
    five = next(p for p in r["predictions"] if p["key"] == "5k")
    assert five["seconds"] == pytest.approx(1200, abs=10)
    half = next(p for p in r["predictions"] if p["key"] == "half")
    assert half["pace_s"] > five["pace_s"] and half["caveat"]
    paces = {p["key"]: p for p in r["paces"]}
    assert paces["easy"]["slow_s"] > paces["threshold"]["slow_s"] > paces["vo2"]["fast_s"]


def test_flat_easy_running_cannot_fake_a_critical_speed():
    r = P.critical_speed(runs_from_curve(3.0, 0), D0 + timedelta(days=10))
    assert not r["valid"] and "3-minute" in r["missing"]
    assert not P.critical_speed([], D0)["valid"]


def test_zone_check_only_trusts_upward_evidence():
    zones = {"floors": [100, 120, 140, 160, 175], "max": 190, "threshold": 168}
    maxes = [(D0, 199.0), (D0, 196.0), (D0, 150.0)]
    r = P.zone_check(zones, maxes, [(D0, 182.0)], D0 + timedelta(days=5))
    assert r["status"] == "stale" and {i["key"] for i in r["issues"]} == {"max", "threshold"}
    assert r["observed_max"] == 196 and r["lthr_estimate"] == 173
    easy = P.zone_check(zones, [(D0, 170.0), (D0, 168.0)], [(D0, 150.0)], D0)
    assert easy["status"] == "ok"
    assert P.zone_check(None, [], [], D0) is None


def test_analyse_run_collects_drift_fade_and_form():
    s = stream(5400, 3.0, hr=lambda x: 135 + x / 250)
    s["cadence"] = [172.0] * len(s["t"])
    r = P.analyse_run(s)
    assert r["decoupling_pct"] > 5 and r["late_fade"]["fade_pct"] > 5
    assert r["form"]["cadence"] == 172 and r["best"]["180"] == pytest.approx(3.0)
    assert r["hr_max"] >= 150 and r["hr20"] > 140


def test_form_trend_compares_cadence_at_the_same_speed():
    def pts(start: int, cadence_shift: float):
        return [{"day": D0 + timedelta(days=start + i * 5), "speed": 2.6 + (i % 4) * 0.2, "cadence": 160 + (i % 4) * 4 + cadence_shift} for i in range(10)]
    r = P.form_trend(pts(0, 0) + pts(100, 5), D0 + timedelta(days=150))
    assert r["cadence_now"] - r["cadence_before"] == 5
