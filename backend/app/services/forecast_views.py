"""Read models for the Forecast Workspace, hierarchy and Model Performance pages."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from app import db
from app.forecasting.models import MODEL_REGISTRY
from app.forecasting.profiling import localize_reason
from app.metrics import bias_class, forecast_accuracy
from app.reconciliation.hierarchy import RECONCILERS
from app.services import ptbr
from app.services.context import (
    PlanningContext,
    backtest_metrics,
    clean,
    filter_ids,
    horizon_totals,
    records,
    timeline,
)

LEVELS = ["company", "region", "channel", "customer", "category", "brand", "sku"]
COMPANY_LABEL = "Empresa (total)"


def _series_row(ctx: PlanningContext, series_id: str) -> pd.Series:
    s = ctx.series.set_index("series_id")
    if series_id not in s.index:
        raise KeyError(series_id)
    return s.loc[series_id]


def series_list(ctx: PlanningContext, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    ids = filter_ids(ctx, filters)
    s = ctx.series[ctx.series["series_id"].isin(ids)].copy()
    a = ctx.actuals[ctx.actuals["date"].isin(ctx.ltm_dates)].groupby("series_id")[["units", "revenue"]].sum()
    s["units_ltm"] = s["series_id"].map(a["units"])
    s["revenue_ltm"] = s["series_id"].map(a["revenue"])
    if ctx.has_run:
        f = ctx.forecast.groupby("series_id")[["p50", "consensus"]].sum()
        s["forecast_12m"] = s["series_id"].map(f["p50"])
        s["consensus_12m"] = s["series_id"].map(f["consensus"])
        s["accuracy"] = s["wmape"].map(lambda w: forecast_accuracy(w) if pd.notna(w) else None)
        s["bias_class"] = s["bias"].map(lambda b: bias_class(b) if pd.notna(b) else None)
    cols = [c for c in s.columns if c not in ("candidates",)]
    return records(s[cols].sort_values("revenue_ltm", ascending=False))


def series_detail(ctx: PlanningContext, series_id: str, measure: str = "units") -> dict[str, Any]:
    row = _series_row(ctx, series_id)
    filters = {"customer": row["customer"], "sku": row["sku"]}
    tl = timeline(ctx, filters, measure, history_months=36)
    out: dict[str, Any] = {
        "series_id": series_id,
        "header": clean(
            {
                k: row.get(k)
                for k in (
                    "sku",
                    "product",
                    "customer",
                    "customer_location",
                    "region",
                    "channel",
                    "category",
                    "brand",
                    "customer_potential",
                    "price",
                )
            }
        ),
        "timeline": records(tl),
        "has_run": ctx.has_run,
        "measure": measure,
    }
    if not ctx.has_run:
        return out
    wm, b = row.get("wmape"), row.get("bias")
    prof = db.query_df("SELECT * FROM series_profiles WHERE run_id = ? AND series_id = ?", [ctx.run_id, series_id])
    if len(prof):  # runs saved by older (English) versions
        prof["classification_reason"] = prof["classification_reason"].map(localize_reason)
    reg = db.query_df(
        "SELECT model, status, wmape, bias, mae, rmse, mape, smape, mase, wmape_std, n_folds, fold_wmape, rank, "
        "parameters, champion_flag, challenger_flag, model_version FROM model_registry "
        "WHERE run_id = ? AND series_id = ? ORDER BY rank NULLS LAST, model",
        [ctx.run_id, series_id],
    )
    reg["family"] = reg["model"].map(lambda m: MODEL_REGISTRY[m].family)
    reg["fold_wmape"] = reg["fold_wmape"].map(lambda v: json.loads(v) if v else [])
    reg["parameters"] = reg["parameters"].map(lambda v: json.loads(v) if v else {})
    bt = db.query_df(
        "SELECT model, fold, date, horizon_step, actual, forecast FROM backtest_results "
        "WHERE run_id = ? AND series_id = ? AND model IN (?, ?) ORDER BY model, date",
        [ctx.run_id, series_id, row.get("champion"), row.get("challenger") or ""],
    )
    f = ctx.forecast[ctx.forecast["series_id"] == series_id].sort_values("date")
    first = f.iloc[0] if len(f) else None
    price = float(row.get("price") or 0)
    k = price if measure == "revenue" else 1.0
    ov = ctx.overrides
    if not ov.empty:
        mask = (ov["customer"].isna() | (ov["customer"] == row["customer"])) & (
            ov["sku"].isna() | (ov["sku"] == row["sku"])
        )
        ov = ov[mask].copy()
        # event types / planners saved by older (English) versions are shown with the Portuguese label
        ov["event_type"] = ov["event_type"].map(lambda v: ptbr.label(ptbr.EVENT_TYPE, v))
        ov["created_by"] = ov["created_by"].map(lambda v: ptbr.label(ptbr.PLANNER, v))
    out.update(
        {
            "selection": clean(
                {
                    "series_type": row.get("series_type"),
                    "classification_reason": prof["classification_reason"].iloc[0] if len(prof) else None,
                    "champion": row.get("champion"),
                    "challenger": row.get("challenger"),
                    "wmape": wm,
                    "accuracy": forecast_accuracy(wm) if pd.notna(wm) else None,
                    "bias": b,
                    "bias_class": bias_class(b) if pd.notna(b) else None,
                    "challenger_wmape": row.get("challenger_wmape"),
                    "confidence": row.get("confidence"),
                    "confidence_score": row.get("confidence_score"),
                    "stability": row.get("wmape_std"),
                    "history_months": row.get("history_months"),
                    "candidates": json.loads(row.get("candidates") or "[]"),
                }
            ),
            "next_month": None
            if first is None
            else clean(
                {
                    "date": first["date"],
                    "base": first["p50"] * k,
                    "consensus": first["consensus"] * k,
                    "p10": first["p10"] * k,
                    "p90": first["p90"] * k,
                }
            ),
            "totals": clean(horizon_totals(ctx, pd.Index([series_id]), measure)),
            "leaderboard": records(reg),
            "backtest": records(bt),
            "profile": records(prof.drop(columns=["run_id"]))[0] if len(prof) else None,
            "overrides": records(ov) if not ov.empty else [],
            "baseline_vs_incremental": records(
                f[["date", "p50", "incremental", "consensus"]].assign(
                    p50=lambda d: d["p50"] * k,
                    incremental=lambda d: d["incremental"] * k,
                    consensus=lambda d: d["consensus"] * k,
                )
            ),
        }
    )
    return out


def aggregate_view(ctx: PlanningContext, filters: dict[str, Any] | None, measure: str = "units") -> dict[str, Any]:
    ids = filter_ids(ctx, filters)
    tl = timeline(ctx, filters, measure, history_months=36)
    out = {
        "n_series": len(ids),
        "timeline": records(tl),
        "totals": clean(horizon_totals(ctx, ids, measure)),
        "metrics": clean(backtest_metrics(ctx, ids)),
        "has_run": ctx.has_run,
        "measure": measure,
    }
    if ctx.has_run:
        s = ctx.series[ctx.series["series_id"].isin(ids)]
        out["champions"] = [{"model": k, "count": int(v)} for k, v in s["champion"].value_counts().items()]
        out["confidence"] = [{"level": k, "count": int(v)} for k, v in s["confidence"].value_counts().items()]
        nxt = tl[tl["date"] == ctx.future_dates.min()] if len(ctx.future_dates) else tl.iloc[0:0]
        if len(nxt):
            out["next_month"] = clean(nxt.iloc[0].to_dict())
    return out


def hierarchy_table(
    ctx: PlanningContext, level: str, filters: dict[str, Any] | None, measure: str = "units", method: str = "bottom_up"
) -> dict[str, Any]:
    if level not in LEVELS:
        options = ", ".join(f"{lv} ({ptbr.DIMENSION[lv]})" for lv in LEVELS)
        raise ValueError(f"Nível inválido. Use um destes códigos: {options}")
    ids = filter_ids(ctx, filters)
    s = ctx.series[ctx.series["series_id"].isin(ids)].copy()
    s["company"] = s.get("company", COMPANY_LABEL)
    col = "revenue" if measure == "revenue" else "units"
    a = ctx.actuals[ctx.actuals["series_id"].isin(ids)].merge(s[["series_id", level]], on="series_id")
    ltm = a[a["date"].isin(ctx.ltm_dates)].groupby(level)[col].sum()
    prior = a[a["date"].isin(ctx.ltm_dates - pd.DateOffset(years=1))].groupby(level)[col].sum()
    df = pd.DataFrame({"actual_ltm": ltm, "actual_prior_ltm": prior})
    df["n_series"] = s.groupby(level)["series_id"].count()
    if ctx.has_run:
        f = ctx.forecast[ctx.forecast["series_id"].isin(ids)].merge(s[["series_id", level]], on="series_id")
        mult = f["price"] if measure == "revenue" else 1.0
        f = f.assign(value=f["p50"] * mult, cons=f["consensus"] * mult)
        hist = a.rename(columns={col: "value"})[[level, "date", "value"]]
        reconciler = RECONCILERS.get(method, RECONCILERS["bottom_up"])
        rec = reconciler.reconcile(f[[level, "date", "value"]], hist, level)
        df["forecast_12m"] = rec.groupby(level)["value"].sum()
        df["consensus_12m"] = f.groupby(level)["cons"].sum()
        bt = ctx.backtest[ctx.backtest["series_id"].isin(ids)].merge(s[["series_id", level]], on="series_id")
        g = bt.assign(ae=(bt["forecast"] - bt["actual"]).abs(), e=bt["forecast"] - bt["actual"]).groupby(level)
        df["wmape"] = g["ae"].sum() / g["actual"].sum().replace(0, np.nan)
        df["bias"] = g["e"].sum() / g["actual"].sum().replace(0, np.nan)
        df["growth_vs_ltm"] = df["consensus_12m"] / df["actual_ltm"].replace(0, np.nan) - 1
    if not ctx.plan.empty:
        bcol, tcol = ("budget_revenue", "target_revenue") if measure == "revenue" else ("budget_units", "target_units")
        p = ctx.plan[ctx.plan["series_id"].isin(ids) & ctx.plan["date"].isin(ctx.future_dates)].merge(
            s[["series_id", level]], on="series_id"
        )
        df["budget_12m"] = p.groupby(level)[bcol].sum()
        df["target_12m"] = p.groupby(level)[tcol].sum()
        if "consensus_12m" in df:
            df["gap_vs_budget"] = df["consensus_12m"] - df["budget_12m"]
            df["gap_vs_budget_pct"] = df["gap_vs_budget"] / df["budget_12m"].replace(0, np.nan)
            df["gap_vs_target"] = df["consensus_12m"] - df["target_12m"]
    df.index.name = "member"
    df = df.reset_index().sort_values("actual_ltm", ascending=False)
    return {
        "level": level,
        "method": method,
        "measure": measure,
        "rows": records(df),
        "next_level": LEVELS[LEVELS.index(level) + 1] if level != "sku" else None,
    }


def leaderboard(ctx: PlanningContext, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if not ctx.has_run:
        return []
    ids = filter_ids(ctx, filters)
    reg = db.query_df(
        "SELECT series_id, model, status, rmse, mase, rank, champion_flag, challenger_flag "
        "FROM model_registry WHERE run_id = ?",
        [ctx.run_id],
    )
    reg = reg[reg["series_id"].isin(ids) & (reg["status"] == "ok")]
    bt = db.query_df("SELECT series_id, model, actual, forecast FROM backtest_results WHERE run_id = ?", [ctx.run_id])
    bt = bt[bt["series_id"].isin(ids)]
    bt = bt.assign(ae=(bt["forecast"] - bt["actual"]).abs(), e=bt["forecast"] - bt["actual"])
    g = bt.groupby("model")
    lb = pd.DataFrame(
        {
            "wmape": g["ae"].sum() / g["actual"].sum().replace(0, np.nan),
            "bias": g["e"].sum() / g["actual"].sum().replace(0, np.nan),
            "rmse": np.sqrt(
                g.apply(lambda d: float(np.mean((d["forecast"] - d["actual"]) ** 2)), include_groups=False)
            ),
        }
    )
    r = reg.groupby("model")
    lb["series_evaluated"] = r["series_id"].nunique()
    lb["champion_count"] = r["champion_flag"].sum()
    lb["challenger_count"] = r["challenger_flag"].sum()
    lb["avg_rank"] = r["rank"].mean()
    lb["median_mase"] = r["mase"].median()
    lb["win_rate"] = lb["champion_count"] / lb["series_evaluated"]
    lb["family"] = [MODEL_REGISTRY[m].family for m in lb.index]
    lb = lb.dropna(subset=["wmape"]).sort_values(["wmape"])
    lb["rank"] = np.arange(1, len(lb) + 1)
    lb["accuracy"] = (1 - lb["wmape"]).clip(lower=0)
    lb["bias_class"] = lb["bias"].map(bias_class)
    lb.index.name = "model"
    return records(lb.reset_index())


def model_distribution(ctx: PlanningContext, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    if not ctx.has_run:
        return {"by_model": [], "by_type": [], "by_family": []}
    ids = filter_ids(ctx, filters)
    s = ctx.series[ctx.series["series_id"].isin(ids)].copy()
    s["family"] = s["champion"].map(lambda m: MODEL_REGISTRY[m].family if m in MODEL_REGISTRY else "n/d")
    by_type = s.groupby(["series_type", "champion"]).size().reset_index(name="count")
    return {
        "by_model": [{"model": k, "count": int(v)} for k, v in s["champion"].value_counts().items()],
        "by_family": [{"family": k, "count": int(v)} for k, v in s["family"].value_counts().items()],
        "by_type": records(by_type),
        "confidence": [{"level": k, "count": int(v)} for k, v in s["confidence"].value_counts().items()],
    }


def heatmap(ctx: PlanningContext, metric: str = "wmape", filters: dict[str, Any] | None = None) -> dict[str, Any]:
    ids = filter_ids(ctx, filters)
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    if not ctx.has_run or s.empty:
        return {"customers": [], "skus": [], "cells": []}
    metric = metric if metric in ("wmape", "bias") else "wmape"
    customers = s.groupby("customer")["series_id"].count().sort_values(ascending=False).index.tolist()
    skus = sorted(s["sku"].unique().tolist())
    cells = []
    for r in s.itertuples():
        v = getattr(r, metric)
        cells.append(
            {
                "customer": r.customer,
                "sku": r.sku,
                "product": r.product,
                "value": clean(v),
                "class": bias_class(v) if metric == "bias" and pd.notna(v) else None,
                "champion": r.champion,
                "series_id": r.series_id,
            }
        )
    return {"metric": metric, "customers": customers, "skus": skus, "cells": cells}


def performance_table(ctx: PlanningContext, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    ids = filter_ids(ctx, filters)
    if not ctx.has_run:
        return []
    s = ctx.series[ctx.series["series_id"].isin(ids)].copy()
    s["gap_vs_challenger"] = s["challenger_wmape"] - s["wmape"]
    s["accuracy"] = (1 - s["wmape"]).clip(lower=0)
    s["bias_class"] = s["bias"].map(lambda b: bias_class(b) if pd.notna(b) else None)
    cols = [
        "series_id",
        "customer",
        "sku",
        "product",
        "region",
        "channel",
        "category",
        "series_type",
        "champion",
        "wmape",
        "accuracy",
        "bias",
        "bias_class",
        "challenger",
        "challenger_wmape",
        "gap_vs_challenger",
        "wmape_std",
        "confidence",
        "confidence_score",
        "history_months",
    ]
    return records(s[cols].sort_values("wmape", ascending=False))


def registry(ctx: PlanningContext, series_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    if not ctx.run_id:
        return []
    sql = (
        "SELECT series_id, model, model_version, training_date, data_cutoff, status, wmape, bias, rmse, mase, "
        "rank, parameters, champion_flag, challenger_flag FROM model_registry WHERE run_id = ?"
    )
    params: list[Any] = [ctx.run_id]
    if series_id:
        sql += " AND series_id = ?"
        params.append(series_id)
    sql += " ORDER BY series_id, rank NULLS LAST LIMIT ?"
    params.append(limit)
    df = db.query_df(sql, params)
    df["parameters"] = df["parameters"].map(lambda v: json.loads(v) if v else {})
    return records(df)
