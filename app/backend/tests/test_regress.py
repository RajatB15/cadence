import numpy as np
import pytest

from cadence_app.analytics import regress as R


def test_ols_recovers_a_slope_and_its_interval():
    rng = np.random.default_rng(1)
    x = rng.normal(size=200)
    y = 2.0 + 0.5 * x + rng.normal(0, 0.3, 200)
    r = R.ols(np.column_stack([np.ones(200), x]), y, lags=3)
    assert r["coef"][1] == pytest.approx(0.5, abs=0.07) and r["ci"][1][0] < 0.5 < r["ci"][1][1] and r["r2"] > 0.6


def test_autocorrelated_noise_widens_the_interval():
    rng = np.random.default_rng(2)
    noise = np.zeros(300)
    for i in range(1, 300):
        noise[i] = 0.9 * noise[i - 1] + rng.normal()
    x = np.column_stack([np.ones(300), np.arange(300) / 300])
    plain, robust = R.ols(x, noise, 0), R.ols(x, noise, 12)
    assert robust["se"][1] > 1.5 * plain["se"][1]


def test_singular_or_tiny_designs_return_none():
    assert R.ols(np.ones((3, 2)), np.ones(3)) is None
    x = np.column_stack([np.ones(20), np.arange(20), 2 * np.arange(20)])
    assert R.ols(x, np.arange(20.0)) is None


def test_blocked_cv_prefers_the_true_model():
    rng = np.random.default_rng(3)
    x = np.column_stack([np.ones(100), rng.normal(size=100)])
    y = 1 + 2 * x[:, 1] + rng.normal(0, 0.2, 100)
    good = R.blocked_cv_rmse(R.lstsq_predict, x, y)
    bad = R.blocked_cv_rmse(R.lstsq_predict, x[:, :1], y)
    assert good < 0.5 * bad
