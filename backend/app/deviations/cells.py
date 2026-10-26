"""Plan-lens cells at series × month grain on the FULL grid ids × months (spec §4.2.2).

One row per (series_id, date) of ``pd.MultiIndex.from_product([ids, months])``; every source is
left-joined onto that grid, so a missing plan row counts as Q_ref = R_ref = 0, a missing actuals row
(ac_pl) as units = revenue = 0 with p_ac = p_fc,i, and a missing forecast row as 0. A left join from
the actuals would drop the budgeted cells without a sale (19 cells on the demo: V −3,40 instead of
−3,58 mi), which is why the grid is mandatory.

The company-wide frame of each comparison (all series × the comparison window) is built once per
context and cached (``common.cached``); ``plan_cells`` slices it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.context import PlanningContext

from . import common

# Columns of the frame returned by ``plan_cells`` (contract for plan.py and the story builder).
PLAN_CELL_COLUMNS = [
    "series_id",
    "date",
    "q_stat",  # fc_*: p50 | ac_pl: actual units
    "q_cons",  # fc_*: consensus | ac_pl: actual units
    "q_inc",  # fc_*: incremental | ac_pl: 0
    "sigma",  # fc_*: sigma (units) | ac_pl: NaN
    "p_x",  # compared-side price: fc_* p_fc,i | ac_pl p_ac,c
    "x_rev",  # X^r
    "x_units",  # X^u
    "q_ref",  # reference units (fc_pl/ac_pl budget, fc_tg target)
    "r_ref",  # reference revenue
    "budget_units",  # kept for the fc_tg challenge step
    "budget_revenue",
    "target_units",
    "target_revenue",
    "ly_rev",  # actuals at t − 12 months
    "ly_units",
    "f_bt",  # ac_pl only: champion backtest forecast (units), NaN when absent
    "promotion",  # ac_pl only: actual promotion flag
    "p_fc",  # p_fc,i: the series' forecast price (median regular price of the last 6 months)
    "has_plan",  # True when a plan row exists for the cell
]

PLAN_VALUE_COLUMNS = ["budget_units", "target_units", "budget_revenue", "target_revenue"]
KEY = ["series_id", "date"]


def _ns(values: object) -> pd.DatetimeIndex:
    """Month timestamps at nanosecond resolution (sources mix [us] and [ns])."""
    return pd.DatetimeIndex(pd.to_datetime(pd.Index(values))).astype("datetime64[ns]")


def _keyed(df: pd.DataFrame, cols: list[str], agg: dict[str, str] | None = None) -> pd.DataFrame:
    """Rows indexed by (series_id, date) with unique keys (duplicates are aggregated)."""
    if df is None or df.empty:
        return pd.DataFrame(columns=cols, index=pd.MultiIndex.from_arrays([[], []], names=KEY))
    out = df[[*KEY, *cols]].copy()
    out["date"] = _ns(out["date"])
    return out.groupby(KEY, sort=False).agg(agg or dict.fromkeys(cols, "sum"))


def _build(ctx: PlanningContext, cmp: str, ids: pd.Index, months: pd.DatetimeIndex) -> pd.DataFrame:
    months = _ns(months)
    grid = pd.MultiIndex.from_product([pd.Index(ids, dtype=object, name="series_id"), months], names=KEY)
    out = pd.DataFrame(index=grid)
    sid = grid.get_level_values("series_id")
    price = ctx.series.set_index("series_id")["price"].astype(float)
    p_fc = pd.Series(sid, index=grid).map(price).fillna(0.0).to_numpy(dtype=float)
    out["p_fc"] = p_fc

    # Plan (budget and target) on the grid; a missing row counts as 0.
    plan = _keyed(ctx.plan, PLAN_VALUE_COLUMNS) if not ctx.plan.empty else None
    if plan is not None and not plan.empty:
        aligned = plan.reindex(grid)
        out["has_plan"] = aligned[PLAN_VALUE_COLUMNS].notna().any(axis=1).to_numpy()
        for c in PLAN_VALUE_COLUMNS:
            out[c] = aligned[c].fillna(0.0).astype(float).to_numpy()
    else:
        out["has_plan"] = False
        for c in PLAN_VALUE_COLUMNS:
            out[c] = 0.0

    # Actuals of the same month one year earlier (LY / PY).
    act = ctx.actuals
    ly = act[["series_id", "date", "units", "revenue"]].copy()
    ly["date"] = _ns(ly["date"]) + pd.DateOffset(months=12)
    ly = _keyed(ly, ["units", "revenue"]).reindex(grid)
    out["ly_units"] = ly["units"].fillna(0.0).astype(float).to_numpy()
    out["ly_rev"] = ly["revenue"].fillna(0.0).astype(float).to_numpy()

    if cmp == "ac_pl":
        a = _keyed(act, ["units", "revenue", "promotion"], {"units": "sum", "revenue": "sum", "promotion": "max"})
        a = a.reindex(grid)
        units = a["units"].fillna(0.0).astype(float).to_numpy()
        revenue = a["revenue"].fillna(0.0).astype(float).to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            p_ac = np.where(units > 0, revenue / np.where(units > 0, units, 1.0), p_fc)
        out["q_stat"] = units
        out["q_cons"] = units
        out["q_inc"] = 0.0
        out["sigma"] = np.nan
        out["p_x"] = p_ac
        out["x_rev"] = revenue
        out["x_units"] = units
        out["promotion"] = a["promotion"].fillna(0.0).astype(float).to_numpy()
        bt = ctx.backtest
        if bt is not None and not bt.empty:
            f = _keyed(bt, ["forecast"], {"forecast": "mean"}).reindex(grid)
            out["f_bt"] = f["forecast"].astype(float).to_numpy()
        else:
            out["f_bt"] = np.nan
        out["q_ref"] = out["budget_units"]
        out["r_ref"] = out["budget_revenue"]
    else:
        fc = _keyed(ctx.forecast, ["p50", "consensus", "incremental", "sigma"]).reindex(grid)
        q_stat = fc["p50"].fillna(0.0).astype(float).to_numpy()
        q_cons = fc["consensus"].fillna(0.0).astype(float).to_numpy()
        out["q_stat"] = q_stat
        out["q_cons"] = q_cons
        out["q_inc"] = fc["incremental"].fillna(0.0).astype(float).to_numpy()
        out["sigma"] = fc["sigma"].fillna(0.0).astype(float).to_numpy()
        out["p_x"] = p_fc
        out["x_rev"] = q_cons * p_fc
        out["x_units"] = q_cons
        out["promotion"] = 0.0
        out["f_bt"] = np.nan
        ref = "target" if cmp == "fc_tg" else "budget"
        out["q_ref"] = out[f"{ref}_units"]
        out["r_ref"] = out[f"{ref}_revenue"]
    return out.reset_index()[PLAN_CELL_COLUMNS]


def plan_cells(ctx: PlanningContext, cmp: str, ids: pd.Index, months: pd.DatetimeIndex) -> pd.DataFrame:
    """Full-grid plan cells for ``cmp`` ∈ {fc_pl, fc_tg, ac_pl} (columns: ``PLAN_CELL_COLUMNS``).

    ``ids × months`` always yields ``len(ids) · len(months)`` rows (row order is not significant);
    ``ids`` outside the context's series still get a row (all zeros).
    """
    if cmp not in common.CMP_PLAN:
        raise common.DeviationError(common.MSG_INVALID_CMP)
    months = _ns(months)
    ids = pd.Index(ids, dtype=object)
    window, _ = common.window(ctx, cmp)
    window = _ns(window)
    all_ids = pd.Index(ctx.series["series_id"], dtype=object)
    if months.isin(window).all() and ids.isin(all_ids).all():
        base = common.cached(ctx, "cells.plan_cells", cmp, build=lambda: _build(ctx, cmp, all_ids, window))
        if len(ids) == len(all_ids) and len(months) == len(window):
            return base.copy()
        keep = base["series_id"].isin(ids) & base["date"].isin(months)
        return base[keep].reset_index(drop=True)
    return _build(ctx, cmp, ids, months)
