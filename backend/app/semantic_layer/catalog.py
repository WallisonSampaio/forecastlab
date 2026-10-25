"""Semantic layer: governed metric & dimension catalog plus a tiny query engine.

The AI Analyst never writes free SQL. It resolves a question to a
(metric, dimension, filters, period) request that this layer executes
deterministically against DuckDB-backed data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from app.services.context import PlanningContext, filter_ids

METRICS: dict[str, dict[str, Any]] = {
    "actual": {"label": "Actual", "format": "measure", "description": "Historical sales (sell-in), units or revenue."},
    "forecast": {
        "label": "Statistical Forecast",
        "format": "measure",
        "description": "Champion-model base forecast (P50), before commercial overrides.",
    },
    "consensus": {
        "label": "Consensus Forecast",
        "format": "measure",
        "description": "Statistical forecast + commercial overrides (incremental demand).",
    },
    "budget": {"label": "Budget", "format": "measure", "description": "Annual budget (financial plan)."},
    "target": {"label": "Sales Target", "format": "measure", "description": "Commercial sales target."},
    "wmape": {
        "label": "WMAPE",
        "format": "percent",
        "description": "Weighted MAPE = sum|F-A| / sum|A| over the rolling-origin backtest (lower is better).",
    },
    "accuracy": {"label": "Forecast Accuracy", "format": "percent", "description": "1 - WMAPE (floored at 0)."},
    "bias": {
        "label": "Bias",
        "format": "percent",
        "description": "sum(F-A) / sum(A). Positive = over-forecast, negative = under-forecast.",
    },
    "gap_vs_budget": {"label": "Gap vs Budget", "format": "measure", "description": "Consensus - Budget."},
    "gap_vs_target": {"label": "Gap vs Target", "format": "measure", "description": "Consensus - Target."},
    "uplift": {
        "label": "Incremental (events)",
        "format": "measure",
        "description": "Consensus - Statistical: demand added by commercial events.",
    },
    "fva": {
        "label": "Forecast Value Added",
        "format": "percent",
        "description": "WMAPE(statistical) - WMAPE(consensus) on overridden cells.",
    },
    "distribution": {
        "label": "Numeric Distribution",
        "format": "number",
        "description": "% of stores listing the SKU.",
    },
    "price": {"label": "Average Net Price", "format": "currency", "description": "Revenue / Units."},
    "p10": {"label": "P10", "format": "measure", "description": "Pessimistic quantile of the forecast."},
    "p90": {"label": "P90", "format": "measure", "description": "Optimistic quantile of the forecast."},
}

DIMENSIONS: dict[str, dict[str, str]] = {
    "period": {"label": "Month", "column": "date"},
    "region": {"label": "Region", "column": "region"},
    "channel": {"label": "Channel", "column": "channel"},
    "customer": {"label": "Customer", "column": "customer"},
    "category": {"label": "Category", "column": "category"},
    "brand": {"label": "Brand", "column": "brand"},
    "sku": {"label": "SKU", "column": "sku"},
    "model": {"label": "Model", "column": "champion"},
    "scenario": {"label": "Scenario", "column": "scenario"},
}


@dataclass
class SemanticQuery:
    metric: str
    by: str = "sku"
    filters: dict[str, Any] = field(default_factory=dict)
    months: list[str] = field(default_factory=list)
    measure: str = "revenue"
    order: str = "desc"
    limit: int = 10

    def describe(self) -> str:
        where = " AND ".join(f"{k} = '{v}'" for k, v in self.filters.items() if v) or "all"
        period = f" PERIOD {', '.join(self.months)}" if self.months else ""
        return (
            f"SELECT {self.metric}({self.measure}) BY {self.by} WHERE {where}{period} "
            f"ORDER BY {self.metric} {self.order.upper()} LIMIT {self.limit}"
        )


def run_query(ctx: PlanningContext, q: SemanticQuery) -> pd.DataFrame:
    """Execute a semantic query; returns columns [member, value, volume, ...]."""
    if q.metric not in METRICS:
        raise ValueError(f"Unknown metric '{q.metric}'")
    if q.by not in DIMENSIONS:
        raise ValueError(f"Unknown dimension '{q.by}'")
    ids = filter_ids(ctx, q.filters)
    col = DIMENSIONS[q.by]["column"]
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    months = pd.DatetimeIndex([pd.Timestamp(m) for m in q.months]) if q.months else None

    if q.metric in ("wmape", "accuracy", "bias"):
        bt = ctx.backtest[ctx.backtest["series_id"].isin(ids)].merge(s[["series_id", col]], on="series_id")
        if months is not None:
            bt = bt[bt["date"].isin(months)]
        bt = bt.assign(ae=(bt["forecast"] - bt["actual"]).abs(), e=bt["forecast"] - bt["actual"])
        g = bt.groupby(col)
        denom = g["actual"].sum().replace(0, np.nan)
        df = pd.DataFrame({"wmape": g["ae"].sum() / denom, "bias": g["e"].sum() / denom, "volume": g["actual"].sum()})
        df["accuracy"] = (1 - df["wmape"]).clip(lower=0)
        df["value"] = df[q.metric]
        df["series"] = s.groupby(col)["series_id"].count()
    elif q.metric in (
        "forecast",
        "consensus",
        "uplift",
        "p10",
        "p90",
        "gap_vs_budget",
        "gap_vs_target",
        "budget",
        "target",
    ):
        months = months if months is not None else ctx.future_dates
        f = ctx.forecast[ctx.forecast["series_id"].isin(ids) & ctx.forecast["date"].isin(months)]
        f = f.merge(s[["series_id", col]], on="series_id")
        k = f["price"] if q.measure == "revenue" else 1.0
        f = f.assign(
            forecast=f["p50"] * k,
            consensus=f["consensus"] * k,
            uplift=f["incremental"] * k,
            p10=f["p10"] * k,
            p90=f["p90"] * k,
        )
        df = f.groupby(col)[["forecast", "consensus", "uplift", "p10", "p90"]].sum()
        if not ctx.plan.empty:
            bc, tc = (
                ("budget_revenue", "target_revenue") if q.measure == "revenue" else ("budget_units", "target_units")
            )
            p = ctx.plan[ctx.plan["series_id"].isin(ids) & ctx.plan["date"].isin(months)].merge(
                s[["series_id", col]], on="series_id"
            )
            df["budget"] = p.groupby(col)[bc].sum()
            df["target"] = p.groupby(col)[tc].sum()
            df["gap_vs_budget"] = df["consensus"] - df["budget"]
            df["gap_vs_target"] = df["consensus"] - df["target"]
        df["value"] = df[q.metric]
        df["volume"] = df["consensus"]
    elif q.metric in ("actual", "price", "distribution"):
        a = ctx.actuals[ctx.actuals["series_id"].isin(ids)]
        a = a[a["date"].isin(months if months is not None else ctx.ltm_dates)].merge(
            s[["series_id", col]], on="series_id"
        )
        g = a.groupby(col)
        df = pd.DataFrame(
            {"units": g["units"].sum(), "revenue": g["revenue"].sum(), "distribution": g["distribution"].mean()}
        )
        df["price"] = df["revenue"] / df["units"].replace(0, np.nan)
        df["actual"] = df["revenue"] if q.measure == "revenue" else df["units"]
        df["value"] = df[q.metric]
        df["volume"] = df["actual"]
    else:
        raise ValueError(f"Metric '{q.metric}' is not queryable by dimension")
    df = df.dropna(subset=["value"])
    df = df.sort_values("value", ascending=q.order == "asc")
    df.index.name = "member"
    return df.reset_index().head(q.limit)


def catalog() -> dict[str, Any]:
    return {"metrics": METRICS, "dimensions": DIMENSIONS}
