from datetime import date, timedelta

from cadence_app.analytics.weight import project, smooth, summarize


def _series(start: date, values: list[float]) -> list[tuple[date, float]]:
    return [(start + timedelta(days=i), v) for i, v in enumerate(values)]


def test_smoothing_reduces_noise_and_tracks_level():
    noisy = [80 + (0.6 if i % 2 else -0.6) for i in range(40)]
    points = smooth(_series(date(2026, 1, 1), noisy))
    assert abs(points[-1].trend_kg - 80) < 0.25
    assert points[-1].band_kg < points[0].band_kg


def test_gap_widens_uncertainty():
    readings = [(date(2026, 1, 1) + timedelta(days=i), 80.0) for i in range(20)]
    after_gap = readings + [(date(2026, 3, 1), 80.0)]
    tight = smooth(readings)[-1].band_kg
    assert smooth(after_gap)[-1].band_kg > tight


def test_projection_on_track_gives_ordered_range():
    today = date(2026, 6, 1)
    p = project(current=80.0, goal=78.0, slope=-0.05, se=0.01, today=today)
    assert p.status == "on_track"
    assert p.expected == today + timedelta(days=40)
    assert p.earliest < p.expected < p.latest


def test_projection_statuses():
    today = date(2026, 6, 1)
    assert project(80.0, 80.05, -0.05, 0.01, today).status == "reached"
    assert project(80.0, 78.0, 0.05, 0.01, today).status == "off_track"
    assert project(80.0, 78.0, -0.01, 0.02, today).status == "flat"
    assert project(80.0, 60.0, -0.01, 0.001, today).status == "too_far"


def test_summary_requires_enough_recent_points():
    readings = _series(date(2026, 1, 1), [80.0, 79.9, 79.8])
    summary = summarize(readings, date(2026, 1, 4), goal=75.0)
    assert summary.projection.status == "insufficient_data"
    assert summary.rate_kg_per_week is None


def test_empty_summary():
    summary = summarize([], date(2026, 1, 1), goal=70.0)
    assert summary.points == [] and summary.projection is None
