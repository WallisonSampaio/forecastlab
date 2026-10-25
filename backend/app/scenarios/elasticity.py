"""Driver sensitivities estimated from history (pooled within-series log-log model).

For each category:

    log(units_it) = a_i + b_p log(price) + b_d log(distribution) + b_promo promo
                    + b_merch merch + b_mkt log(1 + marketing) + month effects + trend + e

Series fixed effects (a_i) are removed with the within transformation, so the
coefficients describe how demand of the *same* series reacts when a driver
moves. Estimates are clipped to plausible ranges and fall back to industry
defaults when data is insufficient.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

DEFAULTS = {
    "price_elasticity": -1.1,
    "distribution_elasticity": 0.8,
    "marketing_elasticity": 0.06,
    "promo_uplift": 0.25,
    "merch_uplift": 0.12,
}
BOUNDS = {
    "price_elasticity": (-3.0, -0.2),
    "distribution_elasticity": (0.2, 1.5),
    "marketing_elasticity": (0.0, 0.3),
    "promo_uplift": (0.0, 1.5),
    "merch_uplift": (0.0, 0.6),
}
MIN_OBS = 60
# Prior standard deviations (log scale) for empirical-Bayes shrinkage: weakly
# identified coefficients (e.g. price when list-price changes coincide with
# seasonality or competitor events) are pulled towards the default.
PRIOR_SD = {
    "price_elasticity": 0.35,
    "distribution_elasticity": 0.35,
    "promo_uplift": 0.20,
    "merch_uplift": 0.12,
    "marketing_elasticity": 0.05,
}


def _prior_mean(name: str) -> float:
    v = DEFAULTS[name]
    return float(np.log1p(v)) if name in ("promo_uplift", "merch_uplift") else v


def _estimate(df: pd.DataFrame) -> dict[str, Any]:
    d = df[(df["units"] > 0) & (df["price"] > 0)].copy()
    cols: dict[str, np.ndarray] = {}
    if d["price"].nunique() > 3:
        cols["price_elasticity"] = np.log(d["price"].to_numpy(float))
    if "distribution" in d and (d["distribution"] > 0).all() and d["distribution"].nunique() > 3:
        cols["distribution_elasticity"] = np.log(d["distribution"].to_numpy(float))
    if "promotion" in d and d["promotion"].sum() >= 5:
        cols["promo_uplift"] = d["promotion"].to_numpy(float)
    if "merchandising_event" in d and d["merchandising_event"].sum() >= 5:
        cols["merch_uplift"] = d["merchandising_event"].to_numpy(float)
    if "marketing_investment" in d and d["marketing_investment"].nunique() > 3:
        cols["marketing_elasticity"] = np.log1p(d["marketing_investment"].to_numpy(float))
    if len(d) < MIN_OBS or not cols:
        return {**DEFAULTS, "source": "default", "n_obs": len(d), "r2": None}
    months = pd.get_dummies(d["date"].dt.month, prefix="m", drop_first=True).to_numpy(float)
    t = ((d["date"] - d["date"].min()).dt.days / 365.25).to_numpy(float)[:, None]
    names = list(cols)
    X = np.column_stack([cols[n] for n in names] + [months, t])
    y = np.log(d["units"].to_numpy(float))
    groups = d["series_id"].to_numpy()
    # Within transformation (series fixed effects).
    Xd = X - pd.DataFrame(X).groupby(groups).transform("mean").to_numpy(float)
    yd = y - pd.Series(y).groupby(groups).transform("mean").to_numpy(float)
    beta, *_ = np.linalg.lstsq(Xd, yd, rcond=None)
    resid = yd - Xd @ beta
    r2 = 1 - float(resid @ resid) / float(yd @ yd) if float(yd @ yd) > 0 else None
    # Cluster-robust (by series) covariance: months of the same series are not independent.
    bread = np.linalg.pinv(Xd.T @ Xd)
    meat = np.zeros_like(bread)
    for g in np.unique(groups):
        idx = groups == g
        s = Xd[idx].T @ resid[idx]
        meat += np.outer(s, s)
    n_groups = len(np.unique(groups))
    scale = n_groups / max(1, n_groups - 1)
    cov = scale * bread @ meat @ bread
    out: dict[str, Any] = {"raw": {}, "std_error": {}}
    for i, n in enumerate(names):
        raw, se = float(beta[i]), float(np.sqrt(max(cov[i, i], 1e-12)))
        # Precision-weighted combination of the estimate and the prior.
        w_data, w_prior = 1 / se**2, 1 / PRIOR_SD[n] ** 2
        v = (raw * w_data + _prior_mean(n) * w_prior) / (w_data + w_prior)
        if n in ("promo_uplift", "merch_uplift"):
            v, raw = float(np.expm1(v)), float(np.expm1(raw))
        lo, hi = BOUNDS[n]
        out[n] = float(np.clip(v, lo, hi))
        out["raw"][n] = round(raw, 4)
        out["std_error"][n] = round(se, 4)
    for n, v in DEFAULTS.items():
        out.setdefault(n, v)
    out.update(source="estimated (shrunk to prior)", n_obs=len(d), r2=None if r2 is None else round(r2, 3))
    return out


@lru_cache(maxsize=4)
def estimate_elasticities(version: str) -> dict[str, dict[str, Any]]:
    from app.services import datasets

    sales = datasets.get_sales(version).sort_values(["customer", "sku", "date"])
    sales["series_id"] = sales["customer"] + "|" + sales["sku"]
    if "promotion" in sales:
        # Regular (shelf) price: promo months carry a discounted net price that would
        # otherwise be confounded with the promotion effect.
        regular = sales["price"].where(sales["promotion"].fillna(0) == 0)
        sales["price"] = regular.groupby(sales["series_id"]).transform(lambda s: s.ffill().bfill())
    out = {"__all__": _estimate(sales)}
    for cat, g in sales.groupby("category"):
        out[str(cat)] = _estimate(g)
    return out


def for_category(elasticities: dict[str, dict[str, Any]], category: str) -> dict[str, Any]:
    return elasticities.get(category) or elasticities.get("__all__") or {**DEFAULTS, "source": "default"}
