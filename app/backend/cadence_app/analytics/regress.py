"""Small regression helpers shared by the Lab analyses (numpy only).

Ordinary least squares with Newey–West (Bartlett kernel) standard errors, because the series here are autocorrelated
(Newey & West 1987): plain OLS errors would make a slow drift look like a significant effect.
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def ols(x: np.ndarray, y: np.ndarray, lags: int = 0) -> dict | None:
    """x: n×k design (include a column of ones yourself). Returns coef, se, 95 % interval, t and R² (None if singular/too small)."""
    n, k = x.shape
    if n <= k + 2:
        return None
    xtx = x.T @ x
    if np.linalg.cond(xtx) > 1e12:
        return None
    inv = np.linalg.inv(xtx)
    beta = inv @ x.T @ y
    resid = y - x @ beta
    u = x * resid[:, None]
    s = u.T @ u
    for lag in range(1, min(lags, n - 1) + 1):
        g = u[lag:].T @ u[:-lag]
        s += (1 - lag / (lags + 1)) * (g + g.T)
    cov = inv @ s @ inv * n / max(n - k, 1)
    se = np.sqrt(np.maximum(np.diag(cov), 0))
    crit = stats.t.ppf(0.975, n - k)
    total = float(np.sum((y - y.mean()) ** 2))
    return {
        "coef": beta, "se": se, "ci": np.column_stack([beta - crit * se, beta + crit * se]),
        "t": np.divide(beta, se, out=np.zeros_like(beta), where=se > 0), "r2": 1 - float(resid @ resid) / total if total > 0 else 0.0, "n": n,
    }


def blocked_cv_rmse(fit_predict, x: np.ndarray, y: np.ndarray, folds: int = 5) -> float:
    """Root mean squared error on held-out contiguous blocks. `fit_predict(x_train, y_train, x_test) -> predictions`."""
    n = len(y)
    sq = 0.0
    for test in np.array_split(np.arange(n), folds):
        train = np.setdiff1d(np.arange(n), test)
        sq += float(np.sum((y[test] - fit_predict(x[train], y[train], x[test])) ** 2))
    return float(np.sqrt(sq / n))


def lstsq_predict(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray) -> np.ndarray:
    beta, *_ = np.linalg.lstsq(x_train, y_train, rcond=None)
    return x_test @ beta
