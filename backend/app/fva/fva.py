"""Forecast Value Added (FVA).

Compares each step of the forecasting process against the previous one on
the last 12 months (the backtest window), cell by cell (Customer x SKU x Month):

    Naive  ->  Statistical (champion, out-of-sample)  ->  Consensus (after overrides)

FVA = error(previous step) - error(this step). Positive values mean the step
*added* value. Error = absolute error; aggregated as WMAPE points.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app import db
from app.services import datasets
from app.services.context import PlanningContext, clean, filter_ids, records

TOLERANCE = 0.005  # changes smaller than 0.5% of actual are "neutral"


def _wmape(err: pd.Series, actual: pd.Series) -> float | None:
    tot = float(actual.abs().sum())
    return float(err.abs().sum() / tot) if tot else None


def evaluate_override(statistical: float, override_pct: float, actual: float) -> dict[str, Any]:
    """FVA of a single override (e.g. stat 100, override +20% -> 120, actual 103)."""
    consensus = statistical * (1 + override_pct)
    err_s, err_c = abs(statistical - actual), abs(consensus - actual)
    fva = err_s - err_c
    tol = TOLERANCE * max(abs(actual), 1e-9)
    outcome = "Improved" if fva > tol else "Worsened" if fva < -tol else "Neutral"
    message = {
        "Improved": "Override improved forecast accuracy.",
        "Worsened": "Override reduced forecast accuracy.",
        "Neutral": "Override had no material effect on accuracy.",
    }[outcome]
    return {
        "statistical": statistical,
        "consensus": consensus,
        "actual": actual,
        "error_statistical": err_s,
        "error_consensus": err_c,
        "fva_units": fva,
        "outcome": outcome,
        "message": message,
    }


def _group(df: pd.DataFrame, key: str) -> list[dict[str, Any]]:
    rows = []
    for k, g in df.groupby(key):
        ws, wc = _wmape(g["forecast"] - g["actual"], g["actual"]), _wmape(g["consensus"] - g["actual"], g["actual"])
        rows.append(
            {
                key: k,
                "overrides": len(g),
                "improved_pct": float((g["outcome"] == "Improved").mean()),
                "wmape_statistical": ws,
                "wmape_consensus": wc,
                "fva_pp": (ws - wc) if ws is not None and wc is not None else None,
                "fva_units": float(g["fva_units"].sum()),
                "avg_adjustment": float(g["adjustment_pct"].mean()),
            }
        )
    return clean(sorted(rows, key=lambda r: -(r["fva_pp"] or 0)))


def fva_report(ctx: PlanningContext, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    if not ctx.has_run:
        return {"available": False, "message": "Run a forecast first."}
    ids = filter_ids(ctx, filters)
    bt = ctx.backtest[ctx.backtest["series_id"].isin(ids)].copy()
    naive = db.query_df(
        "SELECT series_id, date, forecast AS naive FROM backtest_results WHERE run_id = ? AND model = 'Naive'",
        [ctx.run_id],
    )
    naive["date"] = pd.to_datetime(naive["date"])
    cells = bt.merge(naive, on=["series_id", "date"], how="left")
    cells["naive"] = cells["naive"].fillna(cells["forecast"])

    ov = datasets.get_historical_overrides(ctx.version)
    pending = len(ctx.overrides)
    if ov.empty:
        cells["adjustment_pct"] = 0.0
        merged = cells.assign(consensus=cells["forecast"])
        detail = pd.DataFrame()
    else:
        ov["series_id"] = ov["customer"] + "|" + ov["sku"]
        agg = (
            ov.groupby(["series_id", "date"])
            .agg(
                adjustment_pct=("adjustment_pct", "sum"),
                planner=("planner", "first"),
                event_type=("event_type", "first"),
                comment=("comment", "first"),
            )
            .reset_index()
        )
        merged = cells.merge(agg, on=["series_id", "date"], how="left")
        merged["adjustment_pct"] = merged["adjustment_pct"].fillna(0.0)
        merged["consensus"] = (merged["forecast"] * (1 + merged["adjustment_pct"])).clip(lower=0)
        detail = merged[merged["planner"].notna()].copy()

    stair = {
        "naive": _wmape(merged["naive"] - merged["actual"], merged["actual"]),
        "statistical": _wmape(merged["forecast"] - merged["actual"], merged["actual"]),
        "consensus": _wmape(merged["consensus"] - merged["actual"], merged["actual"]),
    }
    stair["fva_statistical_vs_naive"] = (
        (stair["naive"] - stair["statistical"]) if None not in (stair["naive"], stair["statistical"]) else None
    )
    stair["fva_consensus_vs_statistical"] = (
        (stair["statistical"] - stair["consensus"]) if None not in (stair["statistical"], stair["consensus"]) else None
    )

    monthly = []
    for d, g in merged.groupby("date"):
        monthly.append(
            {
                "date": d,
                "naive": _wmape(g["naive"] - g["actual"], g["actual"]),
                "statistical": _wmape(g["forecast"] - g["actual"], g["actual"]),
                "consensus": _wmape(g["consensus"] - g["actual"], g["actual"]),
            }
        )

    out: dict[str, Any] = {
        "available": True,
        "stairstep": clean(stair),
        "monthly": clean(monthly),
        "cells_evaluated": len(merged),
        "pending_overrides": pending,
    }
    if detail.empty:
        out.update(
            summary={"overrides": 0},
            by_planner=[],
            by_event_type=[],
            by_direction=[],
            by_magnitude=[],
            overrides=[],
            examples=[],
        )
        return out

    ev = [
        evaluate_override(s, a, y)
        for s, a, y in zip(detail["forecast"], detail["adjustment_pct"], detail["actual"], strict=True)
    ]
    detail = detail.reset_index(drop=True).join(
        pd.DataFrame(ev)[["error_statistical", "error_consensus", "fva_units", "outcome", "message"]]
    )
    detail["direction"] = np.where(detail["adjustment_pct"] >= 0, "Upward", "Downward")
    detail["magnitude"] = pd.cut(
        detail["adjustment_pct"].abs(), [-1, 0.10, 0.20, 10], labels=["< 10%", "10-20%", "> 20%"]
    ).astype(str)
    detail = detail.merge(
        ctx.series[["series_id", "customer", "sku", "product", "region", "channel"]], on="series_id", how="left"
    )
    ws = _wmape(detail["forecast"] - detail["actual"], detail["actual"])
    wc = _wmape(detail["consensus"] - detail["actual"], detail["actual"])
    out["summary"] = clean(
        {
            "overrides": len(detail),
            "improved": int((detail["outcome"] == "Improved").sum()),
            "worsened": int((detail["outcome"] == "Worsened").sum()),
            "neutral": int((detail["outcome"] == "Neutral").sum()),
            "value_added_pct": float((detail["outcome"] == "Improved").mean()),
            "wmape_statistical_overridden": ws,
            "wmape_consensus_overridden": wc,
            "fva_pp_overridden": (ws - wc) if ws is not None and wc is not None else None,
            "fva_units": float(detail["fva_units"].sum()),
        }
    )
    out["by_planner"] = _group(detail, "planner")
    out["by_event_type"] = _group(detail, "event_type")
    out["by_direction"] = _group(detail, "direction")
    out["by_magnitude"] = _group(detail, "magnitude")
    out["by_customer"] = _group(detail, "customer")
    cols = [
        "date",
        "customer",
        "sku",
        "product",
        "planner",
        "event_type",
        "comment",
        "adjustment_pct",
        "forecast",
        "consensus",
        "actual",
        "error_statistical",
        "error_consensus",
        "fva_units",
        "outcome",
        "direction",
    ]
    detail = detail.sort_values("fva_units")
    out["overrides"] = records(detail[cols].rename(columns={"forecast": "statistical"}))
    worst, best = detail.iloc[0], detail.iloc[-1]
    out["examples"] = clean(
        [
            {
                "kind": "worst",
                **{k: worst[k] for k in ("customer", "sku", "date", "planner", "event_type")},
                **evaluate_override(worst["forecast"], worst["adjustment_pct"], worst["actual"]),
            },
            {
                "kind": "best",
                **{k: best[k] for k in ("customer", "sku", "date", "planner", "event_type")},
                **evaluate_override(best["forecast"], best["adjustment_pct"], best["actual"]),
            },
        ]
    )
    return out
