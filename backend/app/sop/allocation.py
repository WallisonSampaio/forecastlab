"""Goal allocation: split a total target across a dimension.

Methods
-------
* historical - share of the last 12 months actuals
* potential  - share of growth headroom (customer potential - current volume)
* forecast   - share of the consensus forecast for the horizon
* strategic  - user-defined weights (normalised)
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.context import Z90, PlanningContext, agg_sigma, clean, filter_ids

from .feasibility import classify

METHODS = ["historical", "potential", "forecast", "strategic"]
DIMENSIONS = ["region", "channel", "customer", "category", "sku"]


def _weights(
    ctx: PlanningContext, s: pd.DataFrame, dimension: str, method: str, measure: str, strategic: dict[str, float] | None
) -> pd.Series:
    col = "revenue" if measure == "revenue" else "units"
    ids = s["series_id"]
    members = s.groupby(dimension)["series_id"].count().index
    if method == "historical":
        a = ctx.actuals[ctx.actuals["series_id"].isin(ids) & ctx.actuals["date"].isin(ctx.ltm_dates)]
        w = a.merge(s[["series_id", dimension]], on="series_id").groupby(dimension)[col].sum()
    elif method == "forecast":
        f = ctx.forecast[ctx.forecast["series_id"].isin(ids)].merge(s[["series_id", dimension]], on="series_id")
        val = f["consensus"] * (f["price"] if measure == "revenue" else 1.0)
        w = val.groupby(f[dimension]).sum()
    elif method == "potential":
        ltm = ctx.actuals[ctx.actuals["date"].isin(ctx.ltm_dates)].merge(
            ctx.series[["series_id", "customer"]], on="series_id"
        )
        cust_total = ltm.groupby("customer")["units"].sum()
        series_ltm = ltm.groupby("series_id")["units"].sum()
        sp = s.assign(ltm=s["series_id"].map(series_ltm).fillna(0.0))
        sp["potential"] = sp.apply(
            lambda r: (
                (r["customer_potential"] or 0) * r["ltm"] / cust_total.get(r["customer"], 0)
                if cust_total.get(r["customer"], 0)
                else 0.0
            ),
            axis=1,
        )
        sp["headroom"] = (sp["potential"] - sp["ltm"]).clip(lower=0)
        w = sp.groupby(dimension)["headroom"].sum()
        if w.sum() <= 0:
            w = sp.groupby(dimension)["potential"].sum()
    elif method == "strategic":
        strategic = strategic or {}
        w = pd.Series({m: float(strategic.get(str(m), 0.0)) for m in members})
        if w.sum() <= 0:
            w = pd.Series(1.0, index=members)
    else:
        raise ValueError(f"method must be one of {METHODS}")
    w = w.reindex(members).fillna(0.0).clip(lower=0)
    return w / w.sum() if w.sum() else pd.Series(1.0 / len(members), index=members)


def allocate(
    ctx: PlanningContext,
    dimension: str,
    method: str,
    total_target: float | None = None,
    weights: dict[str, float] | None = None,
    filters: dict[str, Any] | None = None,
    measure: str = "revenue",
) -> dict[str, Any]:
    if dimension not in DIMENSIONS:
        raise ValueError(f"dimension must be one of {DIMENSIONS}")
    ids = filter_ids(ctx, filters)
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    if s.empty:
        return {"rows": [], "total_target": 0}
    col = "revenue" if measure == "revenue" else "units"
    tcol = "target_revenue" if measure == "revenue" else "target_units"
    bcol = "budget_revenue" if measure == "revenue" else "budget_units"
    plan = (
        ctx.plan[ctx.plan["series_id"].isin(ids) & ctx.plan["date"].isin(ctx.future_dates)]
        if not ctx.plan.empty
        else pd.DataFrame(columns=["series_id", tcol, bcol])
    )
    if total_target is None:
        total_target = float(plan[tcol].sum())
    w = _weights(ctx, s, dimension, method, measure, weights)

    f = ctx.forecast[ctx.forecast["series_id"].isin(ids)].merge(s[["series_id", dimension]], on="series_id")
    mult = f["price"] if measure == "revenue" else 1.0
    f = f.assign(cons=f["consensus"] * mult, base=f["p50"] * mult, sig=f["sigma"] * mult)
    a = ctx.actuals[ctx.actuals["series_id"].isin(ids) & ctx.actuals["date"].isin(ctx.ltm_dates)].merge(
        s[["series_id", dimension]], on="series_id"
    )
    p = plan.merge(s[["series_id", dimension]], on="series_id")
    rows = []
    for member, weight in w.items():
        fm = f[f[dimension] == member]
        cons, base = float(fm["cons"].sum()), float(fm["base"].sum())
        sig = agg_sigma(fm["sig"]) * (cons / base if base else 1.0)
        alloc = float(total_target) * float(weight)
        cls, prob = classify(alloc, cons, sig, max(0.0, cons - Z90 * sig), cons + Z90 * sig)
        ltm = float(a.loc[a[dimension] == member, col].sum())
        rows.append(
            {
                "member": member,
                "weight": float(weight),
                "allocated_target": alloc,
                "consensus": cons,
                "actual_ltm": ltm,
                "current_target": float(p.loc[p[dimension] == member, tcol].sum()),
                "budget": float(p.loc[p[dimension] == member, bcol].sum()),
                "gap": cons - alloc,
                "gap_pct": (cons / alloc - 1) if alloc else None,
                "required_growth": (alloc / ltm - 1) if ltm else None,
                "probability": prob,
                "classification": cls,
            }
        )
    rows.sort(key=lambda r: -r["allocated_target"])
    return clean(
        {"dimension": dimension, "method": method, "measure": measure, "total_target": total_target, "rows": rows}
    )
