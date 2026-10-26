"""Exploratory Demand Analysis and series profiling views."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from app import db
from app.forecasting.panel import build_panel
from app.forecasting.profiling import localize_reason, profile_series
from app.services.context import PlanningContext, clean, filter_ids, records


def demand_overview(ctx: PlanningContext, filters: dict[str, Any] | None, measure: str = "units") -> dict[str, Any]:
    ids = filter_ids(ctx, filters)
    col = "revenue" if measure == "revenue" else "units"
    a = ctx.actuals[ctx.actuals["series_id"].isin(ids)]
    monthly = a.groupby("date")[col].sum().sort_index()
    full = pd.date_range(monthly.index.min(), ctx.last_actual, freq="MS") if len(monthly) else monthly.index
    monthly = monthly.reindex(full, fill_value=0.0)

    trend = monthly.rolling(12, center=True, min_periods=12).mean()
    # 2x12 centred moving average for even windows (classical decomposition).
    trend = trend.rolling(2, min_periods=2).mean().shift(-1) if len(monthly) >= 24 else trend
    ratio = (monthly / trend).dropna()
    season_idx = ratio.groupby(ratio.index.month).mean()
    season_idx = season_idx / season_idx.mean() if len(season_idx) else season_idx
    rolling_cv = (monthly.rolling(12).std() / monthly.rolling(12).mean()).dropna()

    yoy = None
    if len(monthly) >= 24:
        ltm, prior = monthly.iloc[-12:].sum(), monthly.iloc[-24:-12].sum()
        yoy = float(ltm / prior - 1) if prior else None

    # Promotion effect: units relative to each series' own median, promo vs non-promo months.
    rel = a.assign(rel=a["units"] / a.groupby("series_id")["units"].transform("median").replace(0, np.nan))
    promo_effect = None
    if rel["promotion"].fillna(0).sum() > 0:
        on = rel.loc[rel["promotion"] > 0, "rel"].mean()
        off = rel.loc[rel["promotion"] == 0, "rel"].mean()
        promo_effect = {
            "promo_index": clean(on),
            "no_promo_index": clean(off),
            "uplift": clean(on / off - 1 if off else None),
            "promo_share": clean(float((rel["promotion"] > 0).mean())),
        }
    merch_effect = None
    if rel["merchandising_event"].fillna(0).sum() > 0:
        on = rel.loc[rel["merchandising_event"] > 0, "rel"].mean()
        off = rel.loc[rel["merchandising_event"] == 0, "rel"].mean()
        merch_effect = {"uplift": clean(on / off - 1 if off else None)}

    # Distribution relationship: sample of (distribution, relative units) points.
    dist_points: list[list[float]] = []
    dist_corr = None
    d = rel.dropna(subset=["distribution", "rel"])
    d = d[d["distribution"] > 0]
    if len(d) > 10:
        dist_corr = clean(float(np.corrcoef(d["distribution"], d["rel"])[0, 1]))
        sample = d.sample(min(600, len(d)), random_state=7)
        dist_points = [
            [round(float(x), 1), round(float(y), 3)] for x, y in zip(sample["distribution"], sample["rel"], strict=True)
        ]

    by_dim = {}
    ltm = a[a["date"].isin(ctx.ltm_dates)].merge(
        ctx.series[["series_id", "category", "channel", "region"]], on="series_id"
    )
    for dim in ("category", "channel", "region"):
        g = ltm.groupby(dim)[col].sum().sort_values(ascending=False)
        by_dim[dim] = [{"name": k, "value": clean(v)} for k, v in g.items()]

    zero_share = float((a["units"] == 0).mean()) if len(a) else 0.0
    return {
        "measure": measure,
        "monthly": [
            {"date": d.strftime("%Y-%m-%d"), "value": clean(v), "trend": clean(trend.get(d))}
            for d, v in monthly.items()
        ],
        "seasonality": [{"month": int(m), "index": clean(v)} for m, v in season_idx.items()],
        "volatility": [{"date": d.strftime("%Y-%m-%d"), "cv": clean(v)} for d, v in rolling_cv.items()],
        "kpis": {
            "total_ltm": clean(monthly.iloc[-12:].sum()) if len(monthly) else None,
            "yoy_growth": clean(yoy),
            "seasonal_amplitude": clean(float(season_idx.max() - season_idx.min())) if len(season_idx) else None,
            "peak_month": int(season_idx.idxmax()) if len(season_idx) else None,
            "volatility_cv": clean(float(rolling_cv.iloc[-1])) if len(rolling_cv) else None,
            "zero_demand_share": clean(zero_share),
            "n_series": len(ids),
        },
        "promotion": promo_effect,
        "merchandising": merch_effect,
        "distribution": {"corr": dist_corr, "points": dist_points},
        "breakdown": by_dim,
    }


@lru_cache(maxsize=4)
def _profiles_on_the_fly(version: str) -> pd.DataFrame:
    from app.services import datasets

    panel = build_panel(datasets.get_sales(version), horizon=1)
    rows = []
    for s in panel:
        p = profile_series(
            s.y,
            s.X["promotion"].to_numpy() if "promotion" in s.X else None,
            s.X["distribution"].to_numpy() if "distribution" in s.X else None,
        )
        rows.append({"series_id": s.series_id, "customer": s.customer, "sku": s.sku, **p})
    return pd.DataFrame(rows)


def series_profiles(ctx: PlanningContext, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    ids = filter_ids(ctx, filters)
    if ctx.run_id:
        prof = db.query_df("SELECT * FROM series_profiles WHERE run_id = ?", [ctx.run_id]).drop(columns="run_id")
    else:
        prof = _profiles_on_the_fly(ctx.version)
    prof = prof[prof["series_id"].isin(ids)].merge(
        ctx.series[["series_id", "region", "channel", "category", "brand", "product"]], on="series_id", how="left"
    )
    if "champion" in ctx.series:
        prof = prof.merge(ctx.series[["series_id", "champion", "wmape", "confidence"]], on="series_id", how="left")
    if "classification_reason" in prof:  # runs saved by older (English) versions
        prof["classification_reason"] = prof["classification_reason"].map(localize_reason)
    counts = prof["series_type"].value_counts()
    keep = [c for c in prof.columns if c not in ("candidate_models", "break_index")]
    return {
        "types": [{"type": k, "count": int(v)} for k, v in counts.items()],
        "intermittency": [{"class": k, "count": int(v)} for k, v in prof["intermittency"].value_counts().items()],
        "rows": records(prof[keep].sort_values(["series_type", "customer", "sku"])),
    }
