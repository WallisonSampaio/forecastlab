"""Forecast accuracy metrics.

Conventions
-----------
* ``error = forecast - actual`` (positive error = over-forecast).
* WMAPE is the primary KPI: sum(|error|) / sum(|actual|).
* Bias is relative: sum(error) / sum(actual) -> +5% means 5% over-forecast.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

ArrayLike = Sequence[float] | np.ndarray

BIAS_THRESHOLD = 0.05


def _arr(x: ArrayLike) -> np.ndarray:
    return np.asarray(x, dtype=float)


def mae(actual: ArrayLike, forecast: ArrayLike) -> float:
    a, f = _arr(actual), _arr(forecast)
    return float(np.mean(np.abs(f - a))) if a.size else math.nan


def rmse(actual: ArrayLike, forecast: ArrayLike) -> float:
    a, f = _arr(actual), _arr(forecast)
    return float(np.sqrt(np.mean((f - a) ** 2))) if a.size else math.nan


def mape(actual: ArrayLike, forecast: ArrayLike) -> float:
    """Mean absolute percentage error; periods with zero actuals are excluded."""
    a, f = _arr(actual), _arr(forecast)
    mask = a != 0
    if not mask.any():
        return math.nan
    return float(np.mean(np.abs((f[mask] - a[mask]) / a[mask])))


def smape(actual: ArrayLike, forecast: ArrayLike) -> float:
    """Symmetric MAPE in [0, 2]; 0/0 periods count as perfect."""
    a, f = _arr(actual), _arr(forecast)
    if not a.size:
        return math.nan
    denom = np.abs(a) + np.abs(f)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(denom == 0, 0.0, 2 * np.abs(f - a) / denom)
    return float(np.mean(ratio))


def wmape(actual: ArrayLike, forecast: ArrayLike) -> float:
    a, f = _arr(actual), _arr(forecast)
    total = np.sum(np.abs(a))
    if total == 0:
        return 0.0 if np.allclose(f, 0) else math.nan
    return float(np.sum(np.abs(f - a)) / total)


def bias(actual: ArrayLike, forecast: ArrayLike) -> float:
    a, f = _arr(actual), _arr(forecast)
    total = np.sum(a)
    if total == 0:
        return 0.0 if np.allclose(f, 0) else math.nan
    return float(np.sum(f - a) / total)


def mase(actual: ArrayLike, forecast: ArrayLike, insample: ArrayLike, m: int = 12) -> float:
    """Mean absolute scaled error vs. in-sample (seasonal) naive.

    Falls back to the one-step naive scale when the series is shorter than
    two seasons or the seasonal scale is zero.
    """
    a, f, y = _arr(actual), _arr(forecast), _arr(insample)
    scale = math.nan
    if y.size > m:
        scale = float(np.mean(np.abs(y[m:] - y[:-m])))
    if not scale or math.isnan(scale):
        scale = float(np.mean(np.abs(np.diff(y)))) if y.size > 1 else math.nan
    if not scale or math.isnan(scale):
        return math.nan
    return float(np.mean(np.abs(f - a)) / scale)


def forecast_accuracy(wmape_value: float) -> float:
    """Forecast Accuracy = 1 - WMAPE, floored at 0 (undefined -> NaN)."""
    if wmape_value is None or math.isnan(wmape_value):
        return math.nan
    return max(0.0, 1.0 - wmape_value)


def bias_class(bias_value: float, threshold: float = BIAS_THRESHOLD) -> str:
    """'Under' (< -threshold), 'Balanced' or 'Over' (> +threshold)."""
    if bias_value is None or math.isnan(bias_value):
        return "Balanced"
    if bias_value > threshold:
        return "Over"
    if bias_value < -threshold:
        return "Under"
    return "Balanced"


def all_metrics(actual: ArrayLike, forecast: ArrayLike, insample: ArrayLike | None = None, m: int = 12) -> dict:
    out = {
        "mae": mae(actual, forecast),
        "rmse": rmse(actual, forecast),
        "mape": mape(actual, forecast),
        "smape": smape(actual, forecast),
        "wmape": wmape(actual, forecast),
        "bias": bias(actual, forecast),
    }
    out["mase"] = mase(actual, forecast, insample, m) if insample is not None else math.nan
    out["accuracy"] = forecast_accuracy(out["wmape"])
    return out
