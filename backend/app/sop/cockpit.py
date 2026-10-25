"""S&OP Executive Cockpit and Overview KPIs."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.metrics import bias_class
from app.services.context import (
    PlanningContext,
    backtest_metrics,
    clean,
    filter_ids,
    horizon_totals,
    records,
    timeline,
)

from .feasibility import assess, feasibility_by


def _gap_tables(ctx: PlanningContext, ids: pd.Index, measure: str, by: str = "series_id", top: int = 8):
    bcol = "budget_revenue" if measure == "revenue" else "budget_units"
    f = ctx.forecast[ctx.forecast["series_id"].isin(ids)].copy()
    f["cons"] = f["consensus"] * (f["price"] if measure == "revenue" else 1.0)
    cons = f.groupby("series_id")["cons"].sum()
    p = ctx.plan[ctx.plan["series_id"].isin(ids) & ctx.plan["date"].isin(ctx.future_dates)]
    bud = p.groupby("series_id")[bcol].sum()
    df = pd.DataFrame({"consensus": cons, "budget": bud}).fillna(0.0)
    df["gap"] = df["consensus"] - df["budget"]
    df = df.join(
        ctx.series.set_index("series_id")[
            ["customer", "sku", "product", "region", "channel", "category", "series_type", "champion", "confidence"]
        ]
    )
    if by != "series_id":
        df = df.groupby(by)[["consensus", "budget", "gap"]].sum()
    df["gap_pct"] = df["gap"] / df["budget"].where(df["budget"] != 0)
    df.index.name = "key"
    df = df.reset_index()
    risk = df[df["gap"] < 0].sort_values("gap").head(top)
    opp = df[df["gap"] > 0].sort_values("gap", ascending=False).head(top)
    return df, risk, opp


def cockpit(ctx: PlanningContext, filters: dict[str, Any] | None = None, measure: str = "revenue") -> dict[str, Any]:
    if not ctx.has_run:
        return {"available": False}
    ids = filter_ids(ctx, filters)
    t = horizon_totals(ctx, ids, measure)
    m = backtest_metrics(ctx, ids)
    df, risk, opp = _gap_tables(ctx, ids, measure)
    budget, target, cons = t.get("budget") or 0.0, t.get("target") or 0.0, t["consensus"]
    kpis = {
        "actual_ltm": t["actual_ltm"],
        "actual_growth": (t["actual_ltm"] / t["actual_prior_ltm"] - 1) if t["actual_prior_ltm"] else None,
        "statistical": t["base"],
        "consensus": cons,
        "incremental": t["incremental"],
        "budget": budget,
        "target": target,
        "p10": t["p10"],
        "p90": t["p90"],
        "gap_vs_budget": cons - budget,
        "gap_vs_budget_pct": (cons / budget - 1) if budget else None,
        "gap_vs_target": cons - target,
        "gap_vs_target_pct": (cons / target - 1) if target else None,
        "risk": float(-df.loc[df["gap"] < 0, "gap"].sum()),
        "opportunity": float(df.loc[df["gap"] > 0, "gap"].sum()),
        "forecast_growth": (cons / t["actual_ltm"] - 1) if t["actual_ltm"] else None,
        **m,
        "bias_class": bias_class(m["bias"]) if m.get("bias") is not None else None,
    }
    tl = timeline(ctx, filters, measure, history_months=24)
    future = tl[tl["date"] > ctx.last_actual].copy()
    future["quarter"] = [f"Q{i // 3 + 1}" for i in range(len(future))]
    quarters = future.groupby("quarter", sort=True)[["base", "consensus", "budget", "target"]].sum().reset_index()
    quarters["gap_vs_budget"] = quarters["consensus"] - quarters["budget"]
    quarters["start"] = future.groupby("quarter")["date"].min().values
    return {
        "available": True,
        "measure": measure,
        "horizon": [d.strftime("%Y-%m-%d") for d in ctx.future_dates],
        "kpis": clean(kpis),
        "timeline": records(tl),
        "quarters": records(quarters),
        "risks": records(risk),
        "opportunities": records(opp),
        "feasibility": assess(ctx, filters, None, measure),
        "feasibility_by_region": feasibility_by(ctx, "region", filters, measure),
        "feasibility_by_channel": feasibility_by(ctx, "channel", filters, measure),
        "gap_by_customer": records(_gap_tables(ctx, ids, measure, by="customer", top=50)[0].sort_values("gap")),
    }


def overview(ctx: PlanningContext, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    from app.alerts.engine import build_alerts

    ids = filter_ids(ctx, filters)
    out: dict[str, Any] = {
        "has_run": ctx.has_run,
        "n_series": len(ids),
        "last_actual": ctx.last_actual.strftime("%Y-%m-%d"),
        "run_id": ctx.run_id,
        "dataset_version": ctx.version,
    }
    if not ctx.has_run:
        return out
    m = backtest_metrics(ctx, ids)
    tr = horizon_totals(ctx, ids, "revenue")
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    over = s[(s["bias"] > 0.05)]
    alerts = build_alerts(ctx)
    risk_skus = {
        a["entity"].get("sku") for a in alerts if a["severity"] in ("critical", "high") and a["entity"].get("sku")
    }
    budget, target = tr.get("budget") or 0.0, tr.get("target") or 0.0
    out["kpis"] = clean(
        {
            "accuracy": m["accuracy"],
            "wmape": m["wmape"],
            "bias": m["bias"],
            "bias_class": bias_class(m["bias"]) if m["bias"] is not None else None,
            "revenue_forecast": tr["consensus"],
            "revenue_statistical": tr["base"],
            "revenue_ltm": tr["actual_ltm"],
            "budget": budget,
            "target": target,
            "budget_gap": tr["consensus"] - budget,
            "budget_gap_pct": (tr["consensus"] / budget - 1) if budget else None,
            "target_gap": tr["consensus"] - target,
            "target_gap_pct": (tr["consensus"] / target - 1) if target else None,
            "risk_skus": len(risk_skus),
            "overforecasted_series": len(over),
            "overforecasted_skus": int(over["sku"].nunique()),
        }
    )
    out["timeline"] = records(timeline(ctx, filters, "revenue", history_months=24))
    out["series_types"] = [{"type": k, "count": int(v)} for k, v in s["series_type"].value_counts().items()]
    out["champions"] = [{"model": k, "count": int(v)} for k, v in s["champion"].value_counts().items()]
    out["confidence"] = [{"level": k, "count": int(v)} for k, v in s["confidence"].value_counts().items()]
    out["alerts"] = alerts[:6]
    out["alert_counts"] = {
        sev: sum(1 for a in alerts if a["severity"] == sev) for sev in ("critical", "high", "medium", "low")
    }
    out["feasibility"] = assess(ctx, filters, None, "revenue")
    return out
