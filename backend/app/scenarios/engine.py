"""What-If / Scenario engine.

Scenario demand for each series-month in scope:

    units = start x (1 + dPrice)^e_price
                  x (min(100, D0 (1 + dDist)) / D0)^e_dist
                  x (1 + promo_uplift)          [promoted months]
                  x (1 + merch_uplift)          [merchandising months]
                  x (1 + dMarketing)^e_mkt
                  x (1 + customer growth) x (1 + market growth)

    revenue = units x price x (1 + dPrice) x (1 - promo discount)   [promo months]

``start`` is the Consensus forecast (default) or the Statistical forecast.
Sensitivities come from ``elasticity.estimate_elasticities`` per category.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from app.services.context import PlanningContext, clean, filter_ids, records

from .elasticity import estimate_elasticities, for_category

LEVERS = ["price", "distribution", "promotion", "merchandising", "marketing", "customer_growth", "market_growth"]


@dataclass
class ScenarioParams:
    price_change_pct: float = 0.0
    distribution_change_pct: float = 0.0
    promo_months: list[str] = field(default_factory=list)
    promo_discount_pct: float = 0.15
    merch_months: list[str] = field(default_factory=list)
    marketing_change_pct: float = 0.0
    customer_growth_pct: float = 0.0
    market_growth_pct: float = 0.0
    scope: dict[str, Any] = field(default_factory=dict)
    base: str = "consensus"  # or "statistical"

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> ScenarioParams:
        d = dict(d or {})
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d and d[k] is not None}
        p = cls(**known)
        p.promo_months = [pd.Timestamp(m).strftime("%Y-%m-01") for m in p.promo_months]
        p.merch_months = [pd.Timestamp(m).strftime("%Y-%m-01") for m in p.merch_months]
        return p

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def simulate_rows(ctx: PlanningContext, params: ScenarioParams) -> pd.DataFrame:
    """Series-month scenario rows (units & revenue, base and scenario)."""
    if not ctx.has_run:
        return pd.DataFrame()
    el = estimate_elasticities(ctx.version)
    f = ctx.forecast.merge(ctx.series[["series_id", "category", "customer", "sku"]], on="series_id", how="left")
    start_col = "p50" if params.base == "statistical" else "consensus"
    f["base_units"] = f[start_col]
    f["base_revenue"] = f["base_units"] * f["price"]

    in_scope = f["series_id"].isin(filter_ids(ctx, params.scope)) if params.scope else pd.Series(True, index=f.index)
    last_dist = (
        ctx.actuals.sort_values("date").groupby("series_id")["distribution"].last()
        if "distribution" in ctx.actuals
        else pd.Series(dtype=float)
    )
    d0 = f["series_id"].map(last_dist).fillna(0.0).to_numpy(float)

    e_price = f["category"].map(lambda c: for_category(el, c)["price_elasticity"]).to_numpy(float)
    e_dist = f["category"].map(lambda c: for_category(el, c)["distribution_elasticity"]).to_numpy(float)
    e_mkt = f["category"].map(lambda c: for_category(el, c)["marketing_elasticity"]).to_numpy(float)
    u_promo = f["category"].map(lambda c: for_category(el, c)["promo_uplift"]).to_numpy(float)
    u_merch = f["category"].map(lambda c: for_category(el, c)["merch_uplift"]).to_numpy(float)

    month = f["date"].dt.strftime("%Y-%m-01")
    promo_on = month.isin(params.promo_months).to_numpy() & in_scope.to_numpy()
    merch_on = month.isin(params.merch_months).to_numpy() & in_scope.to_numpy()
    scope = in_scope.to_numpy()

    with np.errstate(divide="ignore", invalid="ignore"):
        new_dist = np.minimum(100.0, d0 * (1 + params.distribution_change_pct))
        dist_ratio = np.where(d0 > 0, new_dist / np.where(d0 > 0, d0, 1), 1 + params.distribution_change_pct)
    factors = {
        "price": np.where(scope, (1 + params.price_change_pct) ** e_price, 1.0),
        "distribution": np.where(scope, np.clip(dist_ratio, 0, None) ** e_dist, 1.0),
        "promotion": np.where(promo_on, 1 + u_promo, 1.0),
        "merchandising": np.where(merch_on, 1 + u_merch, 1.0),
        "marketing": np.where(scope, (1 + params.marketing_change_pct) ** e_mkt, 1.0),
        "customer_growth": np.where(scope, 1 + params.customer_growth_pct, 1.0),
        "market_growth": np.where(scope, 1 + params.market_growth_pct, 1.0),
    }
    total = np.ones(len(f))
    for v in factors.values():
        total = total * v
    f["scenario_units"] = f["base_units"].to_numpy(float) * total
    price_new = f["price"].to_numpy(float) * np.where(scope, 1 + params.price_change_pct, 1.0)
    f["scenario_revenue"] = f["scenario_units"] * price_new * np.where(promo_on, 1 - params.promo_discount_pct, 1.0)
    # Log-share attribution of the uplift to each lever (exact for multiplicative models).
    logs = {k: np.log(np.clip(v, 1e-9, None)) for k, v in factors.items()}
    log_total = np.log(np.clip(total, 1e-9, None))
    delta = f["scenario_units"].to_numpy(float) - f["base_units"].to_numpy(float)
    for k, lv in logs.items():
        with np.errstate(divide="ignore", invalid="ignore"):
            share = np.where(np.abs(log_total) > 1e-12, lv / log_total, 0.0)
        f[f"contrib_{k}"] = delta * share
    return f


def summarize(ctx: PlanningContext, rows: pd.DataFrame, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    if rows.empty:
        return {"totals": {}, "monthly": [], "drivers": []}
    ids = filter_ids(ctx, filters)
    r = rows[rows["series_id"].isin(ids)]
    p = (
        ctx.plan[ctx.plan["series_id"].isin(ids) & ctx.plan["date"].isin(ctx.future_dates)]
        if not ctx.plan.empty
        else pd.DataFrame()
    )
    totals = {
        "base_units": float(r["base_units"].sum()),
        "base_revenue": float(r["base_revenue"].sum()),
        "units": float(r["scenario_units"].sum()),
        "revenue": float(r["scenario_revenue"].sum()),
        "statistical_units": float(r["p50"].sum()),
        "budget_units": float(p["budget_units"].sum()) if len(p) else None,
        "budget_revenue": float(p["budget_revenue"].sum()) if len(p) else None,
        "target_units": float(p["target_units"].sum()) if len(p) else None,
        "target_revenue": float(p["target_revenue"].sum()) if len(p) else None,
    }

    def pct(a: float | None, b: float | None) -> float | None:
        return None if a is None or not b else a / b - 1

    totals.update(
        vs_base_units=pct(totals["units"], totals["base_units"]),
        vs_base_revenue=pct(totals["revenue"], totals["base_revenue"]),
        vs_budget_units=pct(totals["units"], totals["budget_units"]),
        vs_budget_revenue=pct(totals["revenue"], totals["budget_revenue"]),
        vs_target_units=pct(totals["units"], totals["target_units"]),
        vs_target_revenue=pct(totals["revenue"], totals["target_revenue"]),
    )
    m = r.groupby("date")[["base_units", "scenario_units", "base_revenue", "scenario_revenue"]].sum()
    if len(p):
        m = m.join(p.groupby("date")[["budget_units", "target_units", "budget_revenue", "target_revenue"]].sum())
    drivers = [{"lever": k, "units": float(r[f"contrib_{k}"].sum())} for k in LEVERS]
    return {
        "totals": clean(totals),
        "monthly": records(m.reset_index()),
        "drivers": clean([d for d in drivers if abs(d["units"]) > 1e-6]),
    }


def simulate(ctx: PlanningContext, params: ScenarioParams, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = simulate_rows(ctx, params)
    out = summarize(ctx, rows, filters)
    out["params"] = params.as_dict()
    el = estimate_elasticities(ctx.version)
    out["elasticities"] = clean(el)
    return out


def is_noop(params: ScenarioParams) -> bool:
    return (
        all(
            math.isclose(getattr(params, k), 0.0)
            for k in (
                "price_change_pct",
                "distribution_change_pct",
                "marketing_change_pct",
                "customer_growth_pct",
                "market_growth_pct",
            )
        )
        and not params.promo_months
        and not params.merch_months
    )
