"""Series profiling and demand-pattern classification.

Statistics follow standard demand-planning practice:

* ADI / CV^2 (Syntetos-Boylan) for intermittency.
* STL-based trend and seasonal strength (Hyndman & Athanasopoulos):
  F_T = max(0, 1 - Var(R) / Var(T + R)),  F_S = max(0, 1 - Var(R) / Var(S + R)).
* A single-changepoint test (two-segment mean vs. linear trend) for
  structural changes.
"""

from __future__ import annotations

import math
import warnings
from typing import Any

import numpy as np

SERIES_TYPES = [
    "Stable",
    "Trending",
    "Declining",
    "Seasonal",
    "Intermittent",
    "Promo Driven",
    "Distribution Driven",
    "Structural Change",
    "Volatile",
    "Short History",
    "Inactive",
]

ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49
SEASONAL_THRESHOLD = 0.55
TREND_THRESHOLD = 0.5
VOLATILITY_THRESHOLD = 0.22
SHORT_HISTORY = 24


def _safe_corr(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 3 or np.std(a) < 1e-9 or np.std(b) < 1e-9:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _rolling_median(y: np.ndarray, k: int = 5) -> np.ndarray:
    half = k // 2
    return np.array([np.median(y[max(0, i - half) : i + half + 1]) for i in range(len(y))])


def _structural_break(z: np.ndarray, min_seg: int = 8) -> tuple[bool, int | None, float]:
    n = len(z)
    if n < 2 * min_seg + 4:
        return False, None, 0.0
    t = np.arange(n)
    sse_total = float(np.sum((z - z.mean()) ** 2))
    coef = np.polyfit(t, z, 1)
    sse_lin = float(np.sum((z - np.polyval(coef, t)) ** 2))
    best_k, best_sse = None, math.inf
    for k in range(min_seg, n - min_seg + 1):
        a, b = z[:k], z[k:]
        sse = float(np.sum((a - a.mean()) ** 2) + np.sum((b - b.mean()) ** 2))
        if sse < best_sse:
            best_k, best_sse = k, sse
    if best_k is None or sse_total <= 0:
        return False, None, 0.0
    shift = float(z[best_k:].mean() - z[:best_k].mean())
    is_break = best_sse < 0.55 * sse_lin and best_sse < 0.5 * sse_total and abs(shift) > 0.18
    return is_break, best_k, shift


def profile_series(
    y: np.ndarray,
    promotion: np.ndarray | None = None,
    distribution: np.ndarray | None = None,
) -> dict[str, Any]:
    y = np.asarray(y, dtype=float)
    n = len(y)
    mean = float(y.mean()) if n else 0.0
    std = float(y.std(ddof=1)) if n > 1 else 0.0
    nz = y > 0
    n_nz = int(nz.sum())
    prof: dict[str, Any] = {
        "n_obs": n,
        "mean": mean,
        "median": float(np.median(y)) if n else 0.0,
        "variance": std**2,
        "cv": std / mean if mean > 0 else math.nan,
        "zero_pct": float(1 - n_nz / n) if n else 1.0,
        "adi": n / n_nz if n_nz else math.inf,
        "cv2": float((y[nz].std(ddof=1) / y[nz].mean()) ** 2) if n_nz > 1 else 0.0,
    }

    seasonal = np.zeros(n)
    resid_cv = prof["cv"] if not math.isnan(prof["cv"]) else 0.0
    trend_strength = seasonal_strength = 0.0
    if n >= SHORT_HISTORY and n_nz >= 12:
        from statsmodels.tsa.seasonal import STL

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            stl = STL(y, period=12, robust=True).fit()
        T, S, R = np.asarray(stl.trend), np.asarray(stl.seasonal), np.asarray(stl.resid)
        var_r = np.var(R)
        trend_strength = max(0.0, 1 - var_r / np.var(T + R)) if np.var(T + R) > 0 else 0.0
        seasonal_strength = max(0.0, 1 - var_r / np.var(S + R)) if np.var(S + R) > 0 else 0.0
        seasonal = S
        resid_cv = float(np.std(R) / mean) if mean > 0 else 0.0
    elif n >= 6 and mean > 0:
        t = np.arange(n)
        coef = np.polyfit(t, y, 1)
        fitted = np.polyval(coef, t)
        ss_tot = np.sum((y - mean) ** 2)
        trend_strength = float(1 - np.sum((y - fitted) ** 2) / ss_tot) if ss_tot > 0 else 0.0

    deseason = np.clip(y - seasonal, 0, None)
    slope_pct = 0.0
    if n >= 6 and mean > 0:
        slope = np.polyfit(np.arange(n), deseason, 1)[0]
        slope_pct = float(slope * 12 / mean)

    promo_lift = promo_corr = 0.0
    if promotion is not None and n >= 12:
        p = np.asarray(promotion, dtype=float)[:n]
        if p.sum() >= 3 and (p == 0).sum() >= 3:
            ratio = y / np.clip(_rolling_median(y), 1e-9, None)
            promo_lift = float(ratio[p > 0].mean() / max(ratio[p == 0].mean(), 1e-9) - 1)
            promo_corr = _safe_corr(p, ratio)

    dist_corr = dist_range = 0.0
    if distribution is not None and n >= 12:
        d = np.asarray(distribution, dtype=float)[:n]
        dist_range = float(np.nanmax(d) - np.nanmin(d))
        dist_corr = _safe_corr(d, deseason)

    brk, brk_idx, shift = (False, None, 0.0)
    if n >= SHORT_HISTORY and mean > 0 and n_nz >= 12:
        brk, brk_idx, shift = _structural_break(np.log1p(deseason))

    prof.update(
        {
            "trend_strength": float(trend_strength),
            "seasonal_strength": float(seasonal_strength),
            "trend_slope_pct": slope_pct,
            "residual_cv": float(resid_cv),
            "promo_lift": promo_lift,
            "promo_corr": promo_corr,
            "distribution_corr": dist_corr,
            "distribution_range": dist_range,
            "structural_break": bool(brk),
            "break_index": brk_idx,
            "break_shift_pct": float(math.expm1(shift)) if brk else 0.0,
        }
    )
    stype, reason = classify(prof, y)
    prof["series_type"] = stype
    prof["classification_reason"] = reason
    prof["intermittency"] = (
        "Lumpy"
        if prof["adi"] >= ADI_THRESHOLD and prof["cv2"] >= CV2_THRESHOLD
        else "Intermittent"
        if prof["adi"] >= ADI_THRESHOLD
        else "Erratic"
        if prof["cv2"] >= CV2_THRESHOLD
        else "Smooth"
    )
    return prof


def classify(p: dict[str, Any], y: np.ndarray) -> tuple[str, str]:
    n = p["n_obs"]
    if n >= 6 and float(np.sum(y[-6:])) == 0:
        return "Inactive", "No demand in the last 6 months (possible delisting)"
    if n < SHORT_HISTORY:
        return "Short History", f"Only {n} months of history (< {SHORT_HISTORY})"
    if p["adi"] >= ADI_THRESHOLD:
        return "Intermittent", f"ADI {p['adi']:.2f} >= {ADI_THRESHOLD} ({p['zero_pct']:.0%} zero months)"
    if p["distribution_corr"] >= 0.6 and p["distribution_range"] >= 15:
        return "Distribution Driven", (
            f"Demand tracks numeric distribution (corr {p['distribution_corr']:.2f}, "
            f"range {p['distribution_range']:.0f} pts)"
        )
    if p["structural_break"]:
        return "Structural Change", f"Level shift of {p['break_shift_pct']:+.0%} detected at month {p['break_index']}"
    if p["seasonal_strength"] >= SEASONAL_THRESHOLD:
        return "Seasonal", f"Seasonal strength {p['seasonal_strength']:.2f} >= {SEASONAL_THRESHOLD}"
    if p["promo_lift"] >= 0.35 and p["promo_corr"] >= 0.4:
        return "Promo Driven", f"Promotion lift {p['promo_lift']:+.0%} (corr {p['promo_corr']:.2f})"
    if p["trend_strength"] >= TREND_THRESHOLD and abs(p["trend_slope_pct"]) >= 0.06:
        label = "Trending" if p["trend_slope_pct"] > 0 else "Declining"
        return label, f"Trend strength {p['trend_strength']:.2f}, {p['trend_slope_pct']:+.0%} per year"
    if p["residual_cv"] >= VOLATILITY_THRESHOLD:
        return "Volatile", f"Residual CV {p['residual_cv']:.2f} >= {VOLATILITY_THRESHOLD}"
    return "Stable", f"Low volatility (residual CV {p['residual_cv']:.2f}), no dominant pattern"
