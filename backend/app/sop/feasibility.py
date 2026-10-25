"""Target Feasibility Engine: "Is this target realistic?"

The consensus forecast is treated as a distribution N(consensus, sigma),
where sigma is aggregated from out-of-sample backtest errors. The target is
then judged on:

* probability of achieving it,
* where it sits vs. P10 / P50 / P90,
* required growth vs. historical growth and volatility,
* customer potential (addressable headroom),
* incremental demand already planned through commercial events.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from app.scenarios.elasticity import estimate_elasticities, for_category
from app.services.context import Z90, PlanningContext, clean, filter_ids, horizon_totals

# Largest single-lever move considered commercially plausible within a planning year.
PLAUSIBLE = {"Distribution": 0.20, "Price": 0.08, "Marketing": 0.50}

CLASSES = {
    "REALISTIC": {"color": "green", "emoji": "🟢", "label": "Realistic"},
    "STRETCH": {"color": "yellow", "emoji": "🟡", "label": "Stretch"},
    "AGGRESSIVE": {"color": "red", "emoji": "🔴", "label": "Aggressive"},
    "UNDERESTIMATED": {"color": "blue", "emoji": "🔵", "label": "Underestimated"},
}


def classify(target: float, mean: float, sigma: float, p10: float, p90: float) -> tuple[str, float]:
    """Classification from the probability that demand reaches the target."""
    if target <= 0:
        return "UNDERESTIMATED", 1.0
    if sigma <= 0:
        prob = 1.0 if mean >= target else 0.0
    else:
        prob = float(1 - norm.cdf((target - mean) / sigma))
    if target <= p10 or prob >= 0.9:
        return "UNDERESTIMATED", prob
    if prob >= 0.5:
        return "REALISTIC", prob
    if prob >= 0.2 and target <= p90:
        return "STRETCH", prob
    return "AGGRESSIVE", prob


def _potential(ctx: PlanningContext, ids: pd.Index) -> float | None:
    """Annual unit potential attributable to the selected series.

    Customer potential is shared across a customer's SKUs in proportion to
    each series' share of the customer's last-12-month volume.
    """
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    if "customer_potential" not in s or s["customer_potential"].isna().all():
        return None
    ltm = ctx.actuals[ctx.actuals["date"].isin(ctx.ltm_dates)].merge(
        ctx.series[["series_id", "customer"]], on="series_id"
    )
    cust_total = ltm.groupby("customer")["units"].sum()
    series_ltm = ltm.groupby("series_id")["units"].sum()
    total = 0.0
    for r in s.itertuples():
        if pd.isna(r.customer_potential) or not cust_total.get(r.customer):
            continue
        total += float(r.customer_potential) * float(series_ltm.get(r.series_id, 0.0)) / float(cust_total[r.customer])
    return total or None


def assess(
    ctx: PlanningContext,
    filters: dict[str, Any] | None = None,
    months: list[str] | None = None,
    measure: str = "revenue",
) -> dict[str, Any]:
    if not ctx.has_run:
        return {"available": False, "message": "Run a forecast first."}
    ids = filter_ids(ctx, filters)
    sel_months = (
        pd.DatetimeIndex([pd.Timestamp(m).to_period("M").to_timestamp() for m in months])
        if months
        else ctx.future_dates
    )
    sel_months = sel_months[sel_months.isin(ctx.future_dates)]
    if len(sel_months) == 0:
        return {"available": False, "message": "Selected months are outside the forecast horizon."}
    t = horizon_totals(ctx, ids, measure, sel_months)
    target = t.get("target")
    if target is None:
        return {"available": False, "message": "No target available for this selection."}
    cons, base, budget = t["consensus"], t["base"], t.get("budget") or 0.0
    sigma_c = t["sigma"] * (cons / base if base else 1.0)
    p10c, p90c = max(0.0, cons - Z90 * sigma_c), cons + Z90 * sigma_c
    cls, prob = classify(target, cons, sigma_c, p10c, p90c)

    col = "revenue" if measure == "revenue" else "units"
    a = ctx.actuals[ctx.actuals["series_id"].isin(ids)]
    ly = float(a[a["date"].isin(sel_months - pd.DateOffset(years=1))][col].sum())
    hist_growth = (t["actual_ltm"] / t["actual_prior_ltm"] - 1) if t["actual_prior_ltm"] else None
    required_growth = (target / ly - 1) if ly else None
    forecast_growth = (cons / ly - 1) if ly else None
    monthly = a[a["date"].isin(ctx.ltm_dates)].groupby("date")[col].sum()
    volatility = float(monthly.std() / monthly.mean()) if len(monthly) > 2 and monthly.mean() else None

    reasons: list[str] = []
    capacity_ratio = None
    potential = _potential(ctx, ids)
    if potential:
        target_units = horizon_totals(ctx, ids, "units", sel_months).get("target") or 0.0
        annualized = target_units * 12 / len(sel_months)
        capacity_ratio = annualized / potential
        if capacity_ratio > 1.0:
            reasons.append(f"Target implies {capacity_ratio:.0%} of the customers' addressable potential")
            cls = "AGGRESSIVE"
    if required_growth is not None and hist_growth is not None and prob < 0.5:
        if required_growth > max(2 * abs(hist_growth), hist_growth + 0.15):
            reasons.append(f"Required growth {required_growth:+.1%} is far above historical growth {hist_growth:+.1%}")
            cls = "AGGRESSIVE" if cls == "STRETCH" else cls
    if target > p90c:
        reasons.append("Target is above the P90 of the consensus forecast")
    elif target > cons:
        reasons.append("Target is above the consensus (P50) but inside the P10-P90 range")
    elif target < p10c:
        reasons.append("Target is below the P10 of the consensus forecast - likely underestimated")
    else:
        reasons.append("Target is at or below the consensus forecast")
    if t.get("incremental"):
        reasons.append(f"Consensus already includes {t['incremental']:,.0f} of planned commercial events")

    gap = target - cons
    gap_pct = gap / cons if cons else None
    levers = _levers(ctx, ids, gap_pct, cons, measure, len(sel_months)) if gap > 0 else []
    return clean(
        {
            "available": True,
            "measure": measure,
            "months": [m.strftime("%Y-%m-%d") for m in sel_months],
            "classification": cls,
            "display": CLASSES[cls],
            "probability": prob,
            "target": target,
            "budget": budget,
            "statistical": base,
            "consensus": cons,
            "p10": p10c,
            "p50": cons,
            "p90": p90c,
            "statistical_p10": t["p10"],
            "statistical_p90": t["p90"],
            "planned_events": t.get("incremental"),
            "last_year": ly,
            "historical_growth": hist_growth,
            "required_growth": required_growth,
            "forecast_growth": forecast_growth,
            "volatility_cv": volatility,
            "potential_units": potential,
            "capacity_ratio": capacity_ratio,
            "calibration": {
                "required_incremental_vs_budget": (target / budget - 1) if budget else None,
                "gap_vs_consensus": gap,
                "gap_vs_consensus_pct": gap_pct,
                "budget_vs_consensus_pct": (budget / cons - 1) if cons else None,
            },
            "reasons": reasons,
            "levers": levers,
            "recommendation": _recommendation(cls, gap, gap_pct, measure),
        }
    )


def _levers(
    ctx: PlanningContext, ids: pd.Index, gap_pct: float | None, cons: float, measure: str, n_months: int
) -> list[dict[str, Any]]:
    """Translate the gap into the lever movement that would close it (alone)."""
    if not gap_pct or gap_pct <= 0:
        return []
    el = estimate_elasticities(ctx.version)
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    w = ctx.forecast[ctx.forecast["series_id"].isin(ids)].groupby("series_id")["consensus"].sum()
    cats = s.set_index("series_id")["category"]
    weights = w.groupby(cats.reindex(w.index)).sum()
    weights = weights / weights.sum() if weights.sum() else weights

    def avg(key: str) -> float:
        return (
            float(sum(weights.get(c, 0) * for_category(el, c)[key] for c in weights.index))
            if len(weights)
            else float(for_category(el, "__all__")[key])
        )

    g = 1 + gap_pct
    e_d, e_p, e_m, promo = (
        avg("distribution_elasticity"),
        avg("price_elasticity"),
        avg("marketing_elasticity"),
        avg("promo_uplift"),
    )
    out = [
        {
            "lever": "Distribution",
            "required_change": g ** (1 / e_d) - 1 if e_d > 0 else None,
            "elasticity": e_d,
            "note": "Numeric distribution increase needed",
        },
        {
            "lever": "Price",
            "required_change": g ** (1 / e_p) - 1 if e_p < 0 else None,
            "elasticity": e_p,
            "note": "Price reduction needed (volume effect only; revenue impact differs)",
        },
        {
            "lever": "Marketing",
            "required_change": g ** (1 / e_m) - 1 if e_m > 0 else None,
            "elasticity": e_m,
            "note": "Marketing investment increase needed",
        },
    ]
    if promo > 0 and n_months:
        months_needed = gap_pct * n_months / promo
        out.append(
            {
                "lever": "Promotions",
                "required_change": months_needed,
                "elasticity": promo,
                "note": f"Promoted months needed across the selection (uplift {promo:.0%} per promo month)",
            }
        )
    for o in out:
        rc = o["required_change"]
        o["plausible"] = (
            rc is not None
            and math.isfinite(rc)
            and (abs(rc) <= PLAUSIBLE[o["lever"]] if o["lever"] != "Promotions" else rc <= n_months / 3)
        )
    return out


def _recommendation(cls: str, gap: float, gap_pct: float | None, measure: str) -> str:
    unit = "revenue" if measure == "revenue" else "units"
    if cls == "UNDERESTIMATED":
        return (
            "The target sits below the likely outcome. Consider raising it or reallocating effort to "
            "where targets are aggressive."
        )
    if cls == "REALISTIC":
        return "The target is supported by the consensus forecast. Protect the base: availability and execution."
    if cls == "STRETCH":
        return (
            f"Closing the {gap_pct:+.1%} gap ({gap:,.0f} {unit}) needs incremental commercial actions "
            "(distribution, promotions or marketing). Validate the plan in the S&OP meeting."
        )
    return (
        f"The target requires {gap_pct:+.1%} over the consensus ({gap:,.0f} {unit}). It is statistically "
        "unlikely without structural changes - recalibrate the target or commit concrete growth levers."
    )


def feasibility_by(
    ctx: PlanningContext, dimension: str, filters: dict[str, Any] | None = None, measure: str = "revenue"
) -> list[dict[str, Any]]:
    if not ctx.has_run:
        return []
    ids = filter_ids(ctx, filters)
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    rows = []
    for member, g in s.groupby(dimension):
        t = horizon_totals(ctx, pd.Index(g["series_id"]), measure)
        if not t.get("target"):
            continue
        cons, base = t["consensus"], t["base"]
        sig = t["sigma"] * (cons / base if base else 1.0)
        p10c, p90c = max(0.0, cons - Z90 * sig), cons + Z90 * sig
        cls, prob = classify(t["target"], cons, sig, p10c, p90c)
        rows.append(
            clean(
                {
                    "member": member,
                    "target": t["target"],
                    "budget": t.get("budget"),
                    "consensus": cons,
                    "p10": p10c,
                    "p90": p90c,
                    "probability": prob,
                    "classification": cls,
                    "gap_vs_target": cons - t["target"],
                    "gap_vs_target_pct": (cons / t["target"] - 1),
                    "required_growth": (t["target"] / t["actual_ltm"] - 1) if t["actual_ltm"] else None,
                }
            )
        )
    return sorted(rows, key=lambda r: r["probability"] if r["probability"] is not None else 0)


def probability_curve(mean: float, sigma: float, n: int = 41) -> list[dict[str, float]]:
    if sigma <= 0:
        return []
    xs = np.linspace(max(0.0, mean - 3 * sigma), mean + 3 * sigma, n)
    return [
        {"x": float(x), "pdf": float(norm.pdf(x, mean, sigma)), "p_exceed": float(1 - norm.cdf(x, mean, sigma))}
        for x in xs
    ]
