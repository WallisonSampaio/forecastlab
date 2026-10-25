"""Alert Center: automatic, explained exceptions for the planner.

Every alert carries: issue, affected entity, magnitude, potential impact,
explanation and the recommended investigation.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from app import db
from app.services.context import Z90, PlanningContext, agg_sigma, clean

ALERT_TYPES = {
    "high_error": {"title": "High Forecast Error", "color": "red", "icon": "🔴"},
    "severe_over": {"title": "Severe Overforecast", "color": "red", "icon": "🔴"},
    "severe_under": {"title": "Severe Underforecast", "color": "blue", "icon": "🔵"},
    "target_above_p90": {"title": "Target Above P90", "color": "orange", "icon": "🟠"},
    "structural_change": {"title": "Forecast Structural Change", "color": "orange", "icon": "🟠"},
    "challenger_improving": {"title": "Challenger Model Improving", "color": "yellow", "icon": "🟡"},
    "opportunity": {"title": "Commercial Opportunity", "color": "green", "icon": "🟢"},
}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
MAX_PER_TYPE = 12

_cache: dict[tuple, list[dict[str, Any]]] = {}


def _alert(
    kind: str,
    severity: str,
    entity: dict[str, Any],
    magnitude: str,
    impact: float,
    issue: str,
    explanation: str,
    recommendation: str,
    value: float | None = None,
) -> dict[str, Any]:
    meta = ALERT_TYPES[kind]
    key = "-".join(str(v) for v in entity.values())
    return clean(
        {
            "id": f"{kind}:{key}",
            "type": kind,
            "title": meta["title"],
            "color": meta["color"],
            "icon": meta["icon"],
            "severity": severity,
            "entity": entity,
            "issue": issue,
            "magnitude": magnitude,
            "value": value,
            "potential_impact": impact,
            "explanation": explanation,
            "recommendation": recommendation,
        }
    )


def build_alerts(ctx: PlanningContext) -> list[dict[str, Any]]:
    if not ctx.has_run:
        return []
    key = (ctx.version, ctx.run_id, id(ctx))
    if key in _cache:
        return _cache[key]
    s = ctx.series.set_index("series_id")
    rev12 = ctx.forecast.assign(r=ctx.forecast["consensus"] * ctx.forecast["price"]).groupby("series_id")["r"].sum()
    total_rev = float(rev12.sum()) or 1.0
    alerts: list[dict[str, Any]] = []

    def ent(sid: str) -> dict[str, Any]:
        r = s.loc[sid]
        return {
            "series_id": sid,
            "customer": r["customer"],
            "sku": r["sku"],
            "product": r["product"],
            "region": r["region"],
        }

    # --- accuracy & bias ------------------------------------------------------------------
    cand = []
    for sid, r in s.iterrows():
        w, b, rev = r.get("wmape"), r.get("bias"), float(rev12.get(sid, 0.0))
        if rev / total_rev < 0.001:
            continue
        if pd.notna(w) and w > 0.35:
            sev = "critical" if w > 0.6 and rev / total_rev > 0.005 else "high"
            cand.append(
                (
                    "high_error",
                    rev * w,
                    _alert(
                        "high_error",
                        sev,
                        ent(sid),
                        f"WMAPE {w:.0%}",
                        rev * w,
                        f"Backtest error of {w:.0%} for the champion model ({r['champion']}).",
                        f"Series classified as {r['series_type']}; even the best of {len(json.loads(r['candidates']))} "
                        f"candidate models misses by {w:.0%} on average. Revenue exposed in the next 12 months: "
                        f"{rev:,.0f}.",
                        "Check data quality (outliers, stock-outs), confirm the demand pattern with Sales and consider "
                        "managing this item with safety stock instead of forecast precision.",
                        w,
                    ),
                )
            )
        if pd.notna(b) and abs(b) > 0.15:
            kind = "severe_over" if b > 0 else "severe_under"
            cand.append(
                (
                    kind,
                    rev * abs(b),
                    _alert(
                        kind,
                        "high" if abs(b) > 0.25 else "medium",
                        ent(sid),
                        f"Bias {b:+.0%}",
                        rev * abs(b),
                        f"Systematic {'over' if b > 0 else 'under'}-forecast of {abs(b):.0%} in the backtest.",
                        f"The {r['champion']} forecast has been consistently {'above' if b > 0 else 'below'} actual sales "
                        f"over the last 12 months - a sign of a level change the model is still adapting to.",
                        "Review recent level shifts, delistings or new listings and validate the next months with the "
                        "account team."
                        if b > 0
                        else "Check for unconstrained demand (stock-outs), new distribution or growth not yet captured.",
                        b,
                    ),
                )
            )

    # --- structural change / tracking signal ----------------------------------------------
    bt = ctx.backtest.sort_values("date")
    for sid, g in bt.groupby("series_id"):
        if sid not in s.index:
            continue
        recent = g.tail(6)
        err = (recent["forecast"] - recent["actual"]).to_numpy(float)
        mad = np.mean(np.abs(err)) if len(err) else 0
        ts = float(err.sum() / mad) if mad else 0.0
        r = s.loc[sid]
        rev = float(rev12.get(sid, 0.0))
        if (abs(ts) >= 4.5 or r["series_type"] == "Structural Change") and rev / total_rev > 0.001:
            cand.append(
                (
                    "structural_change",
                    rev * 0.1,
                    _alert(
                        "structural_change",
                        "medium",
                        ent(sid),
                        f"Tracking signal {ts:+.1f}",
                        rev * 0.1,
                        "Demand behaviour changed recently."
                        if r["series_type"] != "Structural Change"
                        else "A level shift was detected in the history.",
                        f"Tracking signal over the last 6 backtest months is {ts:+.1f} (|TS| > 4.5 indicates persistent "
                        f"bias). Series type: {r['series_type']}.",
                        "Confirm the cause (price change, competitor, listing) and decide whether to shorten the "
                        "training window or add a commercial override.",
                        ts,
                    ),
                )
            )

    # --- challenger improving -------------------------------------------------------------
    reg = db.query_df(
        "SELECT series_id, model, fold_wmape, champion_flag, challenger_flag FROM model_registry "
        "WHERE run_id = ? AND (champion_flag OR challenger_flag)",
        [ctx.run_id],
    )
    for sid, g in reg.groupby("series_id"):
        ch = g[g["champion_flag"]]
        cl = g[g["challenger_flag"]]
        if ch.empty or cl.empty or sid not in s.index:
            continue
        fw_ch = json.loads(ch["fold_wmape"].iloc[0] or "[]")
        fw_cl = json.loads(cl["fold_wmape"].iloc[0] or "[]")
        if len(fw_ch) >= 2 and len(fw_cl) >= 2 and fw_cl[-1] < fw_ch[-1] * 0.8 and fw_cl[-2] < fw_ch[-2]:
            rev = float(rev12.get(sid, 0.0))
            if rev / total_rev < 0.002:
                continue
            cand.append(
                (
                    "challenger_improving",
                    rev * (fw_ch[-1] - fw_cl[-1]),
                    _alert(
                        "challenger_improving",
                        "low",
                        ent(sid),
                        f"{fw_cl[-1]:.0%} vs {fw_ch[-1]:.0%}",
                        rev * (fw_ch[-1] - fw_cl[-1]),
                        f"Challenger {cl['model'].iloc[0]} beat champion {ch['model'].iloc[0]} in the two most recent folds.",
                        "Over the full backtest the champion still wins, but recent folds favour the challenger - "
                        "the demand pattern may be shifting.",
                        "Monitor the next cycle; if the challenger keeps winning, promote it to champion.",
                        fw_cl[-1],
                    ),
                )
            )

    # --- target above P90 / opportunity (customer level) -----------------------------------------
    if not ctx.plan.empty:
        f = ctx.forecast.merge(ctx.series[["series_id", "customer", "region"]], on="series_id")
        f = f.assign(cons=f["consensus"] * f["price"], sig=f["sigma"] * f["price"], base=f["p50"] * f["price"])
        p = ctx.plan[ctx.plan["date"].isin(ctx.future_dates)].merge(
            ctx.series[["series_id", "customer"]], on="series_id"
        )
        for cust, g in f.groupby("customer"):
            pc = p[p["customer"] == cust]
            target, budget = float(pc["target_revenue"].sum()), float(pc["budget_revenue"].sum())
            cons, base = float(g["cons"].sum()), float(g["base"].sum())
            sig = agg_sigma(g["sig"]) * (cons / base if base else 1)
            p90 = cons + Z90 * sig
            entity = {"customer": cust, "region": g["region"].iloc[0]}
            if target > p90:
                cand.append(
                    (
                        "target_above_p90",
                        target - cons,
                        _alert(
                            "target_above_p90",
                            "high",
                            entity,
                            f"Target {target / cons - 1:+.0%} vs consensus",
                            target - cons,
                            "The 12-month sales target is above the P90 of the forecast.",
                            f"Target {target:,.0f} vs consensus {cons:,.0f} (P90 {p90:,.0f}). Fewer than 1 in 10 "
                            "plausible outcomes reach this target without new commercial actions.",
                            "Run the Target Feasibility analysis, recalibrate the target or document the growth levers "
                            "(distribution, promotions) needed to close the gap.",
                            target / cons - 1 if cons else None,
                        ),
                    )
                )
            if budget and cons > budget * 1.10:
                cand.append(
                    (
                        "opportunity",
                        cons - budget,
                        _alert(
                            "opportunity",
                            "low",
                            entity,
                            f"Consensus {cons / budget - 1:+.0%} vs budget",
                            cons - budget,
                            "Demand is running ahead of the budget.",
                            f"Consensus {cons:,.0f} vs budget {budget:,.0f}. Momentum (trend, distribution or channel "
                            "growth) is not reflected in the plan.",
                            "Secure supply for the upside, consider raising the target and replicate what is working.",
                            cons / budget - 1,
                        ),
                    )
                )

    by_type: dict[str, list[tuple[float, dict]]] = {}
    for kind, impact, a in cand:
        by_type.setdefault(kind, []).append((impact, a))
    for items in by_type.values():
        items.sort(key=lambda x: -x[0])
        alerts.extend(a for _, a in items[:MAX_PER_TYPE])
    alerts.sort(key=lambda a: (SEVERITY_ORDER[a["severity"]], -(a["potential_impact"] or 0)))
    _cache.clear()
    _cache[key] = alerts
    return alerts


def summary(alerts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(alerts),
        "by_severity": {k: sum(1 for a in alerts if a["severity"] == k) for k in SEVERITY_ORDER},
        "by_type": {k: sum(1 for a in alerts if a["type"] == k) for k in ALERT_TYPES},
    }
