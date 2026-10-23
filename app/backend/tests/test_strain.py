import math
from datetime import date, datetime, timedelta, timezone

import pytest

from cadence_app.analytics import notes
from cadence_app.analytics import strain as S
from tests.test_notes import D0, EASY, act, ctx

MIN = 60_000


def day_points(day: date, workout_hr: float = 150, start_h: int = 7) -> list[tuple[int, float]]:
    """2-minute samples: resting 55 most of the day, a brisk 110-bpm walk for an hour, a 60-minute workout."""
    t0 = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * 1000)
    out = []
    for i in range(0, 24 * 60, 2):
        hr = workout_hr if start_h * 60 <= i < start_h * 60 + 60 else 110 if 12 * 60 <= i < 13 * 60 else 55
        out.append((t0 + i * MIN, float(hr)))
    return out


def test_samples_follow_garmin_descriptors():
    payload = {"heartRateValueDescriptors": [{"key": "heartrate", "index": 0}, {"key": "timestamp", "index": 1}],
               "heartRateValues": [[60, 2000], [None, 1000], [58, 1000]]}
    assert S.samples(payload) == [(1000, 58.0), (2000, 60.0)]
    assert S.samples(None) == [] and S.samples({"heartRateValues": [[1000, 61]]}) == [(1000, 61.0)]


def test_trimp_ignores_sitting_and_counts_workouts():
    pts = day_points(D0)
    start = int(datetime(D0.year, D0.month, D0.day, 7, tzinfo=timezone.utc).timestamp() * 1000)
    total, inside = S.trimp(pts, rest=50, hr_max=190, windows=[(start, start + 60 * MIN)])
    r = (150 - 50) / 140
    assert inside == pytest.approx(60 * r * 0.64 * math.exp(1.92 * r), rel=0.01)
    assert 0 < total - inside < inside / 2  # a brisk hour adds about a third; 22 h at 55 bpm adds nothing
    outside, ins = S.histogram(pts, [(start, start + 60 * MIN)])
    assert S.trimp_from_hist(ins, 50, 190) == pytest.approx(inside, rel=1e-6)
    assert S.trimp_from_hist(outside, 50, 190) + S.trimp_from_hist(ins, 50, 190) == pytest.approx(total, rel=1e-6)


def test_calibration_and_target_bands():
    assert S.calibrate([(100.0, 50.0)] * 12)[0] == pytest.approx(2.0)
    assert S.calibrate([(100.0, 50.0)] * 3) == (S.DEFAULT_SCALE, 3)
    history = {D0 + timedelta(days=i): 100.0 for i in range(28)}
    today = D0 + timedelta(days=28)
    ready = S.target(history, today, 90, "key")
    tired = S.target(history, today, 45, "rest")
    assert ready["low"] > 100 and tired["high"] < 50
    assert S.status(10, tired) == "below" and S.status(500, ready) == "above" and S.status(150, ready) == "in"  # band 138–172
    assert S.target({}, today, 80, "easy") is None


def test_strain_reaches_the_context_and_home():
    days = [D0 + timedelta(days=i) for i in range(40)]
    acts = [act(i, d, EASY, load=80.0) for i, d in enumerate(days)]
    hists = {}
    for i, d in enumerate(days):
        pts = day_points(d)
        start = int(datetime(d.year, d.month, d.day, 7, tzinfo=timezone.utc).timestamp() * 1000)
        hists[d] = S.histogram(pts, [(start, start + 60 * MIN)])
    series = {"resting_hr": {d: 50.0 for d in days}, "hrv": {d: 60.0 + (i % 3) for i, d in enumerate(days)},
              "sleep_score": {d: 80.0 for d in days}, "sleep_hours": {d: 8.0 for d in days}}
    c = ctx(acts, series, days=40, hr_hists=hists)
    st = c["strain"]
    assert st["calibrated_on"] == 40 and st["days"][days[-1]]["workout"] == pytest.approx(80, rel=0.01)
    assert 0 < st["days"][days[-1]]["everyday"] < 40
    b = notes.brief(c)
    assert b["strain"]["band"] and b["strain"]["status"] in {"below", "in", "above"} and b["strain"]["calibrated"]
