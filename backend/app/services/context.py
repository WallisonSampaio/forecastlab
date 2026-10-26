"""Planning context: the joined, cached view every analytical service uses.

It combines (for the active dataset + active forecast run):

* series master data (hierarchy attributes, profile, champion/challenger)
* actuals
* statistical base forecast (P10/P50/P90) and challenger forecast
* commercial overrides -> incremental demand -> consensus forecast
* budget and sales targets
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app import db
from app.forecasting.panel import SERIES_SEP
from app.services import datasets

FILTER_DIMS = ["region", "channel", "customer", "category", "brand", "sku"]
ATTRS = [
    "customer",
    "sku",
    "region",
    "channel",
    "customer_location",
    "customer_potential",
    "product",
    "category",
    "brand",
]
RHO = 0.3  # assumed cross-series / cross-month error correlation when aggregating uncertainty
Z90 = 1.2815515655446004

_cache: dict[tuple, PlanningContext] = {}
_cache_lock = threading.Lock()
_overrides_rev = 0


@dataclass
class PlanningContext:
    version: str
    run_id: str | None
    last_actual: pd.Timestamp
    future_dates: pd.DatetimeIndex
    series: pd.DataFrame
    actuals: pd.DataFrame
    forecast: pd.DataFrame
    challenger: pd.DataFrame
    plan: pd.DataFrame
    overrides: pd.DataFrame
    backtest: pd.DataFrame  # champion backtest rows

    @property
    def has_run(self) -> bool:
        return self.run_id is not None and not self.forecast.empty

    @property
    def ltm_dates(self) -> pd.DatetimeIndex:
        return pd.date_range(self.last_actual - pd.DateOffset(months=11), self.last_actual, freq="MS")


class NoDatasetError(RuntimeError):
    pass


def bump_overrides() -> None:
    global _overrides_rev
    _overrides_rev += 1
    invalidate()


def invalidate() -> None:
    with _cache_lock:
        _cache.clear()


def resolve_run(version: str) -> str | None:
    from app.services import runs

    run_id = db.get_state("active_run")
    if run_id:
        owner = db.scalar(
            "SELECT dataset_version FROM forecast_runs WHERE run_id = ? AND status = 'completed'", [run_id]
        )
        if owner == version:
            return run_id
    run_id = runs.latest_successful_run(version)
    if run_id:
        db.set_state("active_run", run_id)
    return run_id


def get_context() -> PlanningContext:
    version = datasets.active_version()
    if not version:
        raise NoDatasetError("Nenhuma base ativa. Carregue um arquivo ou a base de demonstração.")
    run_id = resolve_run(version)
    key = (version, run_id, _overrides_rev)
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    ctx = _build(version, run_id)
    with _cache_lock:
        _cache.clear()
        _cache[key] = ctx
    return ctx


def _build(version: str, run_id: str | None) -> PlanningContext:
    sales = datasets.get_sales(version)
    sales["series_id"] = sales["customer"] + SERIES_SEP + sales["sku"]
    last_actual = pd.Timestamp(sales["date"].max())
    series = sales.sort_values("date").groupby("series_id", as_index=False).last()[["series_id", *ATTRS]]

    # Recent regular price per series (for revenue conversion of forecasts).
    recent = sales[sales["date"] > last_actual - pd.DateOffset(months=6)]
    regular = recent[recent["promotion"].fillna(0) == 0] if "promotion" in recent else recent
    price = regular.groupby("series_id")["price"].median()
    fallback = sales.groupby("series_id").apply(
        lambda g: g["revenue"].sum() / g["units"].sum() if g["units"].sum() else 0.0, include_groups=False
    )
    series["price"] = series["series_id"].map(price).fillna(series["series_id"].map(fallback)).fillna(0.0)

    actuals = sales[
        [
            "series_id",
            "date",
            "units",
            "revenue",
            "price",
            "promotion",
            "distribution",
            "stockout",
            "marketing_investment",
            "merchandising_event",
        ]
    ].copy()

    plan = datasets.get_plan(version)
    if not plan.empty:
        plan["series_id"] = plan["customer"] + SERIES_SEP + plan["sku"]
        plan = plan[["series_id", "date", "budget_units", "target_units", "budget_revenue", "target_revenue"]]

    overrides = db.query_df("SELECT * FROM overrides WHERE dataset_version = ? ORDER BY date, created_at", [version])
    if not overrides.empty:
        overrides["date"] = pd.to_datetime(overrides["date"])

    future_dates = pd.DatetimeIndex([])
    forecast = pd.DataFrame(columns=["series_id", "date", "model", "p50", "sigma", "p10", "p90"])
    challenger = forecast.copy()
    backtest = pd.DataFrame(columns=["series_id", "date", "actual", "forecast", "fold", "horizon_step"])
    if run_id:
        sel = db.query_df("SELECT * FROM series_selection WHERE run_id = ?", [run_id])
        series = series.merge(sel.drop(columns=["run_id", "customer", "sku"]), on="series_id", how="left")
        fc = db.query_df(
            "SELECT series_id, date, model, role, p50, sigma, p10, p90 FROM forecasts WHERE run_id = ?", [run_id]
        )
        fc["date"] = pd.to_datetime(fc["date"])
        forecast = fc[fc["role"] == "champion"].drop(columns="role").reset_index(drop=True)
        challenger = fc[fc["role"] == "challenger"].drop(columns="role").reset_index(drop=True)
        future_dates = pd.DatetimeIndex(sorted(forecast["date"].unique()))
        backtest = db.query_df(
            "SELECT b.series_id, b.date, b.actual, b.forecast, b.fold, b.horizon_step FROM backtest_results b "
            "JOIN series_selection s ON b.run_id = s.run_id AND b.series_id = s.series_id AND b.model = s.champion "
            "WHERE b.run_id = ?",
            [run_id],
        )
        backtest["date"] = pd.to_datetime(backtest["date"])
        forecast = _apply_overrides(forecast, series, overrides)
        forecast = forecast.merge(series[["series_id", "price"]], on="series_id", how="left")
    return PlanningContext(
        version, run_id, last_actual, future_dates, series, actuals, forecast, challenger, plan, overrides, backtest
    )


def _apply_overrides(forecast: pd.DataFrame, series: pd.DataFrame, overrides: pd.DataFrame) -> pd.DataFrame:
    """Consensus = Base x (1 + sum of uplifts); Incremental = Consensus - Base."""
    f = forecast.copy()
    f["uplift"] = 0.0
    if not overrides.empty:
        attrs = series.set_index("series_id")[["customer", "sku"]]
        cust = f["series_id"].map(attrs["customer"])
        sku = f["series_id"].map(attrs["sku"])
        for o in overrides.itertuples():
            mask = f["date"] == o.date
            if isinstance(o.customer, str) and o.customer:
                mask &= cust == o.customer
            if isinstance(o.sku, str) and o.sku:
                mask &= sku == o.sku
            f.loc[mask, "uplift"] += float(o.uplift_pct)
    f["consensus"] = (f["p50"] * (1 + f["uplift"])).clip(lower=0)
    f["incremental"] = f["consensus"] - f["p50"]
    return f


# ------------------------------------------------------------------------------ helpers
def filter_ids(ctx: PlanningContext, filters: dict[str, Any] | None) -> pd.Index:
    s = ctx.series
    mask = pd.Series(True, index=s.index)
    for dim in FILTER_DIMS:
        val = (filters or {}).get(dim)
        if val is None or val == "" or val == []:
            continue
        values = val if isinstance(val, list | tuple | set) else [val]
        mask &= s[dim].isin([str(v) for v in values])
    return pd.Index(s.loc[mask, "series_id"])


def agg_sigma(sigmas: np.ndarray | pd.Series, rho: float = RHO) -> float:
    s = np.asarray(sigmas, dtype=float)
    s = s[np.isfinite(s)]
    if s.size == 0:
        return 0.0
    return float(math.sqrt(max(0.0, (1 - rho) * np.sum(s**2) + rho * np.sum(s) ** 2)))


def measure_cols(measure: str) -> dict[str, str]:
    return {
        "actual": "revenue" if measure == "revenue" else "units",
        "budget": "budget_revenue" if measure == "revenue" else "budget_units",
        "target": "target_revenue" if measure == "revenue" else "target_units",
    }


def forecast_frame(ctx: PlanningContext, ids: pd.Index, measure: str = "units") -> pd.DataFrame:
    """Series-month forecast rows in the requested measure."""
    f = ctx.forecast[ctx.forecast["series_id"].isin(ids)].copy()
    if measure == "revenue":
        for c in ("p50", "p10", "p90", "sigma", "consensus", "incremental"):
            f[c] = f[c] * f["price"]
    return f


def timeline(
    ctx: PlanningContext, filters: dict[str, Any] | None = None, measure: str = "units", history_months: int = 24
) -> pd.DataFrame:
    ids = filter_ids(ctx, filters)
    cols = measure_cols(measure)
    start = ctx.last_actual - pd.DateOffset(months=history_months - 1)
    end = ctx.future_dates.max() if len(ctx.future_dates) else ctx.last_actual
    dates = pd.date_range(start, end, freq="MS")
    out = pd.DataFrame(index=dates)
    a = ctx.actuals[ctx.actuals["series_id"].isin(ids) & (ctx.actuals["date"] >= start)]
    out["actual"] = a.groupby("date")[cols["actual"]].sum()
    out.loc[out.index > ctx.last_actual, "actual"] = np.nan

    if ctx.has_run:
        f = forecast_frame(ctx, ids, measure)
        g = f.groupby("date")
        out["base"] = g["p50"].sum()
        out["consensus"] = g["consensus"].sum()
        out["incremental"] = g["incremental"].sum()
        sig = g["sigma"].apply(agg_sigma)
        out["p10"] = (out["base"] - Z90 * sig).clip(lower=0)
        out["p90"] = out["base"] + Z90 * sig
        ch = ctx.challenger[ctx.challenger["series_id"].isin(ids)].merge(
            ctx.series[["series_id", "price"]], on="series_id"
        )
        if measure == "revenue":
            ch["p50"] = ch["p50"] * ch["price"]
        out["challenger"] = ch.groupby("date")["p50"].sum()
        bt = ctx.backtest[ctx.backtest["series_id"].isin(ids)].merge(ctx.series[["series_id", "price"]], on="series_id")
        if measure == "revenue":
            bt["forecast"] = bt["forecast"] * bt["price"]
        out["backtest"] = bt.groupby("date")["forecast"].sum()
    if not ctx.plan.empty:
        p = ctx.plan[ctx.plan["series_id"].isin(ids)]
        out["budget"] = p.groupby("date")[cols["budget"]].sum()
        out["target"] = p.groupby("date")[cols["target"]].sum()
    out.index.name = "date"
    return out.reset_index()


def horizon_totals(
    ctx: PlanningContext, ids: pd.Index, measure: str = "units", months: pd.DatetimeIndex | None = None
) -> dict[str, float]:
    """Totals over the forecast horizon (or a subset of months)."""
    cols = measure_cols(measure)
    months = ctx.future_dates if months is None else months
    out: dict[str, float] = {}
    if ctx.has_run:
        f = forecast_frame(ctx, ids, measure)
        f = f[f["date"].isin(months)]
        sig = agg_sigma(f["sigma"])
        base = float(f["p50"].sum())
        cons = float(f["consensus"].sum())
        out.update(
            base=base,
            consensus=cons,
            incremental=cons - base,
            sigma=sig,
            p10=max(0.0, base - Z90 * sig),
            p90=base + Z90 * sig,
            consensus_p10=max(0.0, cons - Z90 * sig * (cons / base if base else 1)),
            consensus_p90=cons + Z90 * sig * (cons / base if base else 1),
        )
    if not ctx.plan.empty:
        p = ctx.plan[ctx.plan["series_id"].isin(ids) & ctx.plan["date"].isin(months)]
        out.update(budget=float(p[cols["budget"]].sum()), target=float(p[cols["target"]].sum()))
    a = ctx.actuals[ctx.actuals["series_id"].isin(ids)]
    ltm = a[a["date"].isin(ctx.ltm_dates)]
    prior = a[a["date"].isin(ctx.ltm_dates - pd.DateOffset(years=1))]
    out["actual_ltm"] = float(ltm[cols["actual"]].sum())
    out["actual_prior_ltm"] = float(prior[cols["actual"]].sum())
    return out


def backtest_metrics(ctx: PlanningContext, ids: pd.Index) -> dict[str, float | None]:
    bt = ctx.backtest[ctx.backtest["series_id"].isin(ids)]
    total = float(bt["actual"].abs().sum())
    if bt.empty or total == 0:
        return {"wmape": None, "bias": None, "accuracy": None}
    w = float((bt["forecast"] - bt["actual"]).abs().sum() / total)
    b = float((bt["forecast"] - bt["actual"]).sum() / bt["actual"].sum())
    return {"wmape": w, "bias": b, "accuracy": max(0.0, 1 - w)}


def series_label(ctx: PlanningContext, sid: str) -> str:
    row = ctx.series.set_index("series_id").loc[sid]
    return f"{row['customer']} · {row['sku']} {row['product']}"


def clean(v: Any) -> Any:
    """JSON-safe conversion for numpy / pandas values."""
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [clean(x) for x in v]
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating | float):
        f = float(v)
        return None if not math.isfinite(f) else f
    if isinstance(v, np.bool_):
        return bool(v)
    if v is pd.NaT:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [clean(r) for r in df.to_dict("records")]
