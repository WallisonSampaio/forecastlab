"""Forecast-error lens of the deep dive: ac_fc (Real × Estatístico campeão) and ac_cs (Real × Consenso
histórico, i.e. the champion forecast with the historical commercial adjustments) — spec §4.2.7, §4.3.3.

Grain: champion backtest cells (Cliente × SKU × mês) of the active run — out of sample, rolling origin,
drivers frozen at the origin. Accuracy is measured in UNITS (WMAPE, bias); impact in R$ at the realized
cell price (E = e · p, AE = |E|). Each cell gets exactly one cause (``rootcause.cell_cause``).

Identities (tested): company ac_fc WMAPE/bias over BT == ``context.backtest_metrics``; Σ causes = total
absolute error; systematic + noise = total; naive WMAPE == ``fva_report().stairstep.naive``.

The four lens functions mirror ``plan.py`` (``exceptions`` takes ``cause`` instead of ``direction``).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app import db
from app.forecasting.panel import SERIES_SEP
from app.metrics import bias_class
from app.services import ptbr
from app.services.context import PlanningContext, clean, filter_ids, records, timeline

from . import common, narrative, rootcause

ERROR_CELL_COLUMNS = [
    "series_id",
    "date",
    "origin",
    "horizon_step",
    "actual",  # A (units)
    "forecast",  # F: statistical (ac_fc) or consensus = clip(F_stat·(1 + adj), 0) (ac_cs)
    "forecast_stat",  # F_stat: champion backtest forecast (units)
    "adj",  # Σ historical adjustment_pct of the cell (0 for ac_fc)
    "e",  # F − A (units)
    "p",  # realized cell price
    "AE",  # |e · p| (R$)
    "cause",  # rootcause.CAUSES code
    "group",  # controllable | inherent | unexplained
    "rmse",  # series RMSE of the statistical forecast over the whole BT window (units) = σ of P10/P90
    "ts",  # series tracking signal of the lens forecast over its last 6 cells (alerts.engine formula)
]
# Extra columns (appended after ERROR_CELL_COLUMNS; consumers must not rely on column positions).
EXTRA_CELL_COLUMNS = [
    "e_stat",  # F_stat − A (units)
    "E",  # e · p (R$, signed)
    "actual_rev",  # A · p (R$)
    "forecast_rev",  # F · p (R$)
    "hist_adj",  # Σ historical adjustment_pct of the cell (also for ac_fc; evidence "sem ajuste registrado")
    "promotion",
    "merchandising_event",
    "stockout",
    "price",  # actual list price of the month
    "price_ref",  # median non-promotion price in [origin − 2, origin] (fallback: series price)
    "distribution",
    "distribution_origin",
    "promotion_origin",
    "series_type",
    "structural_break",
    "break_date",  # first record month + break_index (NaT without a break)
]

# ---------------------------------------------------------------------------------------- constants
MIN_MONTHS = 3  # fewer backtest months in the period -> "interprete com cautela" notice
CONC_SHARE = 0.50  # concentration: smallest k with cumulative share ≥ 50% ...
CONC_MAX = 3  # ... clamped to 1..3
DIRECTION_TOL = 0.10  # cause direction: net > 10% of abs -> over; < −10% -> under; otherwise mixed
TOP_MODELS = 3
# Inherent top cause: the diagnosis and the action buttons also name the leading controllable cause
# when it carries at least this share of the error.
LEAD_CONTROLLABLE_MIN_SHARE = 0.05
PRICE_REF_MONTHS = 2  # price_ref window: [origin − 2, origin]
TS_WINDOW = 6  # tracking signal over the series' last 6 backtest cells (same as alerts.engine)
TIMELINE_MONTHS = 24  # drawer timeline length
NAIVE_MODEL = "Naive"

MSG_NO_BACKTEST = "Sem resultados de backtest para as séries deste recorte."
MSG_NO_RUN_BACKTEST = "Esta execução não tem resultados de backtest."
MSG_EMPTY_NODE = "Nenhuma série neste recorte."
MSG_INVALID_CAUSE = "Causa inválida para a lente de previsão."
NOTE_OUT_OF_SAMPLE = "Real × Previsão medido fora da amostra: backtest com origem móvel e {lag} de antecedência."
NOTE_FEW_MONTHS = "Erro calculado com poucos meses — interprete com cautela."
NOTE_COVERAGE = "{n} de {m} séries do recorte sem backtest (histórico curto) ficam fora desta análise."

KPI_LABEL = {
    "accuracy": "Acurácia",
    "accuracy_cs": "Acurácia do consenso",
    "bias": "Viés",
    "abs_error": "Erro absoluto",
    "top_cause": "Causa principal",
    "fva": "Valor dos ajustes (FVA)",
}

_BT_SQL = (
    "SELECT b.series_id, b.date, b.origin, b.horizon_step, b.actual, b.forecast FROM backtest_results b "
    "JOIN series_selection s ON b.run_id = s.run_id AND b.series_id = s.series_id AND b.model = s.champion "
    "WHERE b.run_id = ?"
)
_ACT_COLS = ["units", "revenue", "price", "promotion", "distribution", "stockout", "merchandising_event"]
_CAUSE_KEYS = [
    "e",
    "actual",
    "forecast",
    "forecast_stat",
    "adj",
    "stockout",
    "promotion",
    "merchandising_event",
    "distribution",
    "distribution_origin",
    "price",
    "price_ref",
    "structural_break",
    "break_date",
    "date",
    "ts",
    "series_type",
    "rmse",
]


# ======================================================================================== cells
def _actuals(ctx: PlanningContext) -> pd.DataFrame:
    """One actuals row per (series_id, date) (sales extracts normally already are)."""
    act = ctx.actuals[["series_id", "date", *_ACT_COLS]]
    if not act.duplicated(["series_id", "date"]).any():
        return act
    agg = {
        "units": "sum",
        "revenue": "sum",
        "price": "mean",
        "promotion": "max",
        "distribution": "mean",
        "stockout": "max",
        "merchandising_event": "max",
    }
    return act.groupby(["series_id", "date"], as_index=False).agg(agg)


def historical_adjustments(ctx: PlanningContext) -> pd.DataFrame:
    """Σ historical ``adjustment_pct`` by (series_id, date) — the consensus of the past cycles (cached)."""

    def build() -> pd.DataFrame:
        hist = db.query_df(
            "SELECT customer, sku, date, adjustment_pct FROM historical_overrides WHERE dataset_version = ?",
            [ctx.version],
        )
        if hist.empty:
            return pd.DataFrame(columns=["series_id", "date", "hist_adj"])
        hist["series_id"] = hist["customer"] + SERIES_SEP + hist["sku"]
        hist["date"] = pd.to_datetime(hist["date"])
        adj = hist.groupby(["series_id", "date"], as_index=False)["adjustment_pct"].sum()
        return adj.rename(columns={"adjustment_pct": "hist_adj"})

    return common.cached(ctx, "historical_adjustments", build=build)


def has_history(ctx: PlanningContext) -> bool:
    """True when the dataset has historical commercial adjustments (ac_cs is computable)."""
    return not historical_adjustments(ctx).empty


def _price_ref(act: pd.DataFrame, keys: pd.DataFrame) -> pd.DataFrame:
    """Median non-promotion price in [origin − 2, origin] per (series_id, origin)."""
    reg = act[(act["promotion"].fillna(0) == 0) & (act["price"].fillna(0) > 0)][["series_id", "date", "price"]]
    m = keys.merge(reg, on="series_id", how="inner")
    lo = m["origin"] - pd.DateOffset(months=PRICE_REF_MONTHS)
    m = m[(m["date"] <= m["origin"]) & (m["date"] >= lo)]
    return m.groupby(["series_id", "origin"], as_index=False)["price"].median().rename(columns={"price": "price_ref"})


def _break_dates(ctx: PlanningContext, act: pd.DataFrame) -> pd.DataFrame:
    """structural_break + break_date (= first record month + break_index months) per series."""
    prof = rootcause._profiles(ctx)
    out = pd.DataFrame(index=pd.Index(ctx.series["series_id"], name="series_id"))
    first = act.groupby("series_id")["date"].min()
    brk = prof["structural_break"].reindex(out.index) if "structural_break" in prof else None
    idx = prof["break_index"].reindex(out.index) if "break_index" in prof else None
    out["structural_break"] = (
        brk.astype("boolean").fillna(False).astype(bool) if brk is not None else pd.Series(False, index=out.index)
    )
    dates = []
    for sid in out.index:
        i = idx.get(sid) if idx is not None else None
        f = first.get(sid)
        ok = bool(out.at[sid, "structural_break"]) and i is not None and not pd.isna(i) and f is not None
        dates.append(pd.Timestamp(f) + pd.DateOffset(months=int(i)) if ok else pd.NaT)
    out["break_date"] = pd.to_datetime(pd.Series(dates, index=out.index))
    return out.reset_index()


def _base_frame(ctx: PlanningContext, kind: str) -> pd.DataFrame:
    """Company-wide champion backtest cells of the run with causes, before filtering (cached per kind)."""
    cols = ERROR_CELL_COLUMNS + EXTRA_CELL_COLUMNS
    if not ctx.run_id:
        return pd.DataFrame(columns=cols)
    bt = db.query_df(_BT_SQL, [ctx.run_id])
    if bt.empty:
        return pd.DataFrame(columns=cols)
    bt["date"] = pd.to_datetime(bt["date"])
    bt["origin"] = pd.to_datetime(bt["origin"])
    bt = bt.rename(columns={"forecast": "forecast_stat"})
    bt["actual"] = bt["actual"].astype(float)
    bt["forecast_stat"] = bt["forecast_stat"].astype(float)

    act = _actuals(ctx)
    bt = bt.merge(act, on=["series_id", "date"], how="left")
    org = act[["series_id", "date", "distribution", "promotion"]].rename(
        columns={"date": "origin", "distribution": "distribution_origin", "promotion": "promotion_origin"}
    )
    bt = bt.merge(org, on=["series_id", "origin"], how="left")
    bt = bt.merge(
        _price_ref(act, bt[["series_id", "origin"]].drop_duplicates()), on=["series_id", "origin"], how="left"
    )
    p_fc = bt["series_id"].map(ctx.series.set_index("series_id")["price"]).astype(float).fillna(0.0)
    bt["price_ref"] = bt["price_ref"].fillna(p_fc)
    units = bt["units"].fillna(0.0)
    bt["p"] = np.where(units > 0, bt["revenue"].fillna(0.0) / units.where(units > 0, 1.0), p_fc)

    bt = bt.merge(historical_adjustments(ctx), on=["series_id", "date"], how="left")
    bt["hist_adj"] = bt["hist_adj"].fillna(0.0).astype(float)
    bt["adj"] = bt["hist_adj"] if kind == "ac_cs" else 0.0
    bt["forecast"] = (bt["forecast_stat"] * (1 + bt["adj"])).clip(lower=0)
    bt["e"] = bt["forecast"] - bt["actual"]
    bt["e_stat"] = bt["forecast_stat"] - bt["actual"]
    bt["E"] = bt["e"] * bt["p"]
    bt["AE"] = bt["E"].abs()
    bt["actual_rev"] = bt["actual"] * bt["p"]
    bt["forecast_rev"] = bt["forecast"] * bt["p"]

    bt["series_type"] = bt["series_id"].map(ctx.series.set_index("series_id")["series_type"])
    bt = bt.merge(_break_dates(ctx, act), on="series_id", how="left")
    bt["structural_break"] = bt["structural_break"].astype("boolean").fillna(False).astype(bool)

    # RMSE of the statistical forecast over the whole window (σ behind P10/P90, worker._interval_sigma)
    rmse = bt.assign(sq=np.square(bt["e_stat"])).groupby("series_id")["sq"].mean().pow(0.5)
    bt["rmse"] = bt["series_id"].map(rmse).fillna(0.0)
    # tracking signal of the lens forecast over the series' last TS_WINDOW cells (alerts.engine formula)
    last = bt.sort_values("date").groupby("series_id").tail(TS_WINDOW)
    last = last.assign(abs_e=last["e"].abs())
    mad = last.groupby("series_id")["abs_e"].mean()
    ts = (last.groupby("series_id")["e"].sum() / mad.where(mad > 0)).fillna(0.0)
    bt["ts"] = bt["series_id"].map(ts).fillna(0.0)

    bt["cause"] = [rootcause.cell_cause(r, kind) for r in bt[_CAUSE_KEYS].to_dict("records")]
    bt["group"] = bt["cause"].map(lambda c: rootcause.CAUSES[c][1])
    return bt[cols].sort_values(["series_id", "date"]).reset_index(drop=True)


def error_cells(ctx: PlanningContext, cmp: str, ids: pd.Index, months: pd.DatetimeIndex) -> pd.DataFrame:
    """Champion backtest cells of ``ids`` × ``months`` for ``cmp`` ∈ {ac_fc, ac_cs}.

    Columns: ERROR_CELL_COLUMNS, then EXTRA_CELL_COLUMNS. Plan comparisons (B1's ac_pl volume split)
    get the ac_fc frame. ``rmse`` and ``ts`` are always computed on the whole BT window, whatever ``months`` is.
    """
    common.validate_cmp(cmp)
    kind = cmp if cmp in common.CMP_FORECAST else "ac_fc"
    base = common.cached(ctx, "error_cells", kind, build=lambda: _base_frame(ctx, kind))
    out = base[base["series_id"].isin(ids) & base["date"].isin(months)]
    return out.reset_index(drop=True)


# ======================================================================================== metrics
def node_metrics(cells: pd.DataFrame) -> dict[str, Any]:
    """Aggregates over a set of cells (spec §4.2.7): WMAPE/bias/accuracy in units, errors in R$,
    systematic = Σ_i |Σ_t E_c| and noise = ΣAE − systematic."""
    a = float(cells["actual"].sum()) if len(cells) else 0.0
    abs_e = float(cells["e"].abs().sum()) if len(cells) else 0.0
    net_e = float(cells["e"].sum()) if len(cells) else 0.0
    ae = float(cells["AE"].sum()) if len(cells) else 0.0
    w = abs_e / a if a > 0 else None
    b = net_e / a if a > 0 else None
    systematic = float(cells.groupby("series_id")["E"].sum().abs().sum()) if len(cells) else 0.0
    systematic = min(systematic, ae)
    return {
        "actual": float(cells["actual_rev"].sum()) if len(cells) else 0.0,
        "forecast": float(cells["forecast_rev"].sum()) if len(cells) else 0.0,
        "actual_units": a,
        "wmape": w,
        "bias": b,
        "accuracy": max(0.0, 1 - w) if w is not None else None,
        "abs_error": ae,
        "net_error": float(cells["E"].sum()) if len(cells) else 0.0,
        "systematic": systematic,
        "noise": max(0.0, ae - systematic),
        "systematic_share": systematic / ae if ae > 0 else None,
        "n_cells": len(cells),
        "n_series": int(cells["series_id"].nunique()) if len(cells) else 0,
    }


def _direction(net: float, abs_: float) -> str:
    if net > DIRECTION_TOL * abs_:
        return "over"
    if net < -DIRECTION_TOL * abs_:
        return "under"
    return "mixed"


def cause_rows(cells: pd.DataFrame) -> list[dict[str, Any]]:
    """CauseRow[] (every cause with ≥ 1 cell), grouped controllable → inherent → unexplained, then by
    absolute error. Σ abs_error = total absolute error; Σ share = 1 (when the total is > 0)."""
    if cells.empty:
        return []
    total = float(cells["AE"].sum())
    grp = cells.groupby("cause")
    g = grp[["AE", "E"]].sum().rename(columns={"AE": "abs_error", "E": "net_error"})
    g["n_cells"] = grp.size()
    g["n_series"] = grp["series_id"].nunique()
    out = []
    for code, (label, group) in rootcause.CAUSES.items():
        if code not in g.index:
            continue
        r = g.loc[code]
        abs_e = float(r["abs_error"])
        out.append(
            {
                "code": code,
                "label": label,
                "group": group,
                "group_label": rootcause.GROUP_LABEL[group],
                "abs_error": abs_e,
                "share": abs_e / total if total > 0 else 0.0,
                "net_error": float(r["net_error"]),
                "direction": _direction(float(r["net_error"]), abs_e),
                "n_cells": int(r["n_cells"]),
                "n_series": int(r["n_series"]),
            }
        )
    out.sort(key=lambda r: (rootcause.GROUP_ORDER.index(r["group"]), -r["abs_error"]))
    return out


def top_cause(causes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Cause with the largest absolute error (ties: rule priority)."""
    if not causes:
        return None
    order = list(rootcause.CAUSES)
    return min(causes, key=lambda r: (-r["abs_error"], order.index(r["code"])))


def lead_controllable(causes: list[dict[str, Any]], cause1: dict[str, Any] | None) -> dict[str, Any] | None:
    """The controllable cause with the largest error, when the top cause is NOT controllable and that
    controllable cause carries at least LEAD_CONTROLLABLE_MIN_SHARE of the error (else None)."""
    if not cause1 or cause1["group"] == "controllable":
        return None
    ctrl = [c for c in causes if c["group"] == "controllable"]
    if not ctrl:
        return None
    lead = max(ctrl, key=lambda r: r["abs_error"])
    return lead if lead["share"] >= LEAD_CONTROLLABLE_MIN_SHARE else None


def group_shares(cells: pd.DataFrame) -> dict[str, float]:
    """{controllable, inherent, unexplained} share of the absolute error (0 when the total is 0)."""
    total = float(cells["AE"].sum()) if len(cells) else 0.0
    by = cells.groupby("group")["AE"].sum() if len(cells) else pd.Series(dtype=float)
    return {g: (float(by.get(g, 0.0)) / total if total > 0 else 0.0) for g in rootcause.GROUP_ORDER}


def naive_wmape(ctx: PlanningContext, ids: pd.Index | None = None, months: pd.DatetimeIndex | None = None):
    """WMAPE of the Naive backtest on the champion cells (merged on series_id, date; missing -> F_stat),
    exactly as ``fva_report`` stairstep 'naive'."""
    cells = error_cells(ctx, "ac_fc", ctx.series["series_id"] if ids is None else ids, _bt(ctx, months))
    if cells.empty:
        return None
    naive = common.cached(ctx, "naive_backtest", build=lambda: _naive_rows(ctx))
    m = cells[["series_id", "date", "actual", "forecast_stat"]].merge(naive, on=["series_id", "date"], how="left")
    m["naive"] = m["naive"].fillna(m["forecast_stat"])
    tot = float(m["actual"].abs().sum())
    return float((m["naive"] - m["actual"]).abs().sum() / tot) if tot else None


def _naive_rows(ctx: PlanningContext) -> pd.DataFrame:
    naive = db.query_df(
        "SELECT series_id, date, forecast AS naive FROM backtest_results WHERE run_id = ? AND model = ?",
        [ctx.run_id, NAIVE_MODEL],
    )
    naive["date"] = pd.to_datetime(naive["date"])
    return naive.drop_duplicates(["series_id", "date"])


def wmape_by_lag(cells: pd.DataFrame) -> list[dict[str, Any]]:
    """[{lag, wmape}] by ``horizon_step`` (units)."""
    out = []
    for lag, g in cells.groupby("horizon_step"):
        a = float(g["actual"].sum())
        out.append({"lag": int(lag), "wmape": float(g["e"].abs().sum() / a) if a > 0 else None})
    return out


def by_model(ctx: PlanningContext, cells: pd.DataFrame, top: int | None = TOP_MODELS) -> list[dict[str, Any]]:
    """[{model, label, abs_error, share, wmape}] grouped by the series' champion, largest error first."""
    if cells.empty:
        return []
    total = float(cells["AE"].sum())
    champ = cells["series_id"].map(ctx.series.set_index("series_id")["champion"]).fillna("—")
    out = []
    for model, g in cells.groupby(champ):
        a = float(g["actual"].sum())
        ae = float(g["AE"].sum())
        out.append(
            {
                "model": str(model),
                "label": ptbr.model(str(model)),
                "abs_error": ae,
                "share": ae / total if total > 0 else 0.0,
                "wmape": float(g["e"].abs().sum() / a) if a > 0 else None,
            }
        )
    out.sort(key=lambda r: -r["abs_error"])
    return out[:top] if top else out


def _bt(ctx: PlanningContext, months: pd.DatetimeIndex | None = None) -> pd.DatetimeIndex:
    return common.backtest_months(ctx) if months is None else pd.DatetimeIndex(months)


# ======================================================================================== shared pieces
def comparisons(ctx: PlanningContext) -> list[dict[str, Any]]:
    """The 'Comparação' options with availability (spec §2.3.3) — the same list as the plan lens
    (``common.comparisons``), so switching lens never changes which comparisons are enabled."""
    return common.comparisons(ctx)


def _period_json(per: common.Period) -> dict[str, Any]:
    return common.period_dict(per)


def _attrs(ctx: PlanningContext) -> pd.DataFrame:
    return common.cached(ctx, "series_attrs", build=lambda: ctx.series.set_index("series_id"))


def _member_of(ctx: PlanningContext, series_ids: pd.Series, level: str) -> pd.Series:
    if level == "series":
        return series_ids.astype(str)
    return series_ids.map(_attrs(ctx)[level]).fillna("—").astype(str)


def _labels(ctx: PlanningContext) -> pd.Series:
    """series_id -> 'Cliente · SKU produto' (cached)."""

    def build() -> pd.Series:
        s = ctx.series
        return pd.Series(
            (s["customer"] + " · " + s["sku"] + " " + s["product"].fillna("")).str.strip().to_numpy(),
            index=s["series_id"].to_numpy(),
        )

    return common.cached(ctx, "series_labels", build=build)


def _series_label(ctx: PlanningContext, sid: str) -> str:
    lbl = _labels(ctx)
    return str(lbl[sid]) if sid in lbl.index else str(sid).replace(SERIES_SEP, " · ")


def member_label(ctx: PlanningContext, level: str | None, key: str | None) -> str:
    """Display label of a breakdown member: series 'Cliente · SKU produto', champion/pattern in pt-BR."""
    if key is None:
        return ""
    if level == "series":
        return _series_label(ctx, key)
    if level == "champion":
        return ptbr.model(key)
    if level == "series_type":
        return ptbr.series_type(key)
    return str(key)


def _restrict(ctx: PlanningContext, ids: pd.Index, level: str, member: str) -> pd.Index:
    if level == "series":
        return ids[ids == member]
    attr = _attrs(ctx)[level]
    keep = attr[attr.astype(str) == str(member)].index
    return ids[ids.isin(keep)]


def _scope(
    ctx: PlanningContext,
    filters: dict[str, Any],
    cmp: str,
    period: str | None,
    focus_level: str | None = None,
    focus: str | None = None,
) -> tuple[common.Period, pd.Index, str | None, str | None]:
    """(period, ids of node ∩ focus, focus level, focus member)."""
    per = common.parse_period(ctx, cmp, period)
    ids = filter_ids(ctx, filters)
    lv = None
    if focus not in (None, ""):
        lv = focus_level or common.next_level(filters)
        ids = _restrict(ctx, ids, lv, str(focus))
    else:
        focus = None
    return per, ids, lv, focus


def _unavailable_reason(ctx: PlanningContext, cmp: str) -> str | None:
    if cmp == "ac_cs" and not has_history(ctx):
        return common.MSG_NO_OVERRIDES
    if ctx.backtest is None or ctx.backtest.empty:
        return MSG_NO_RUN_BACKTEST
    return None


def _rev_share(ctx: PlanningContext) -> pd.Series:
    """Share of each series' consensus revenue over H in the company total (alerts.engine rule)."""

    def build() -> pd.Series:
        f = ctx.forecast
        if f is None or f.empty:
            return pd.Series(dtype=float)
        rev = f.assign(r=f["consensus"] * f["price"]).groupby("series_id")["r"].sum()
        total = float(rev.sum()) or 1.0
        return rev / total

    return common.cached(ctx, "series_rev_share", build=build)


def _series_table(ctx: PlanningContext, cells: pd.DataFrame) -> pd.DataFrame:
    """Per-series aggregates of the cells: units, R$, errors, TS and top cause (+ the month of its largest cell)."""
    if cells.empty:
        return pd.DataFrame(
            columns=[
                "series_id",
                "actual_units",
                "abs_e",
                "net_e",
                "actual",
                "forecast",
                "AE",
                "E",
                "n_cells",
                "ts",
                "top_cause",
                "top_share",
                "top_date",
                "top_dist_change",
            ]
        )
    num = cells[["series_id", "actual", "e", "actual_rev", "forecast_rev", "AE", "E"]].assign(abs_e=cells["e"].abs())
    g = num.groupby("series_id")
    t = g[["actual", "abs_e", "e", "actual_rev", "forecast_rev", "AE", "E"]].sum()
    t.columns = ["actual_units", "abs_e", "net_e", "actual", "forecast", "AE", "E"]
    t["n_cells"] = g.size()
    t["ts"] = cells.groupby("series_id")["ts"].first()
    by_cause = cells.groupby(["series_id", "cause"])["AE"].sum().reset_index()
    order = {c: i for i, c in enumerate(rootcause.CAUSES)}
    by_cause["prio"] = by_cause["cause"].map(order)
    best = by_cause.sort_values(["series_id", "AE", "prio"], ascending=[True, False, True]).drop_duplicates("series_id")
    best = best.set_index("series_id")
    t["top_cause"] = best["cause"]
    t["top_share"] = (best["AE"] / t["AE"].where(t["AE"] > 0)).fillna(0.0)
    # month (and Δ distribution) of the largest cell of the top cause — prefill of the actions
    c2 = cells.merge(best[["cause"]].rename(columns={"cause": "top"}), left_on="series_id", right_index=True)
    c2 = c2[c2["cause"] == c2["top"]].sort_values(["series_id", "AE"], ascending=[True, False])
    c2 = c2.drop_duplicates("series_id").set_index("series_id")
    t["top_date"] = c2["date"]
    t["top_dist_change"] = c2["distribution"] - c2["distribution_origin"]
    return t.reset_index()


def _is_exception(wmape: float | None, bias: float | None, ts: float | None, rev_share: float) -> bool:
    """Forecast exception (spec §4.3.3; constants mirror alerts.engine)."""
    if wmape is not None and wmape >= rootcause.HIGH_ERROR and rev_share >= rootcause.MIN_REV_SHARE:
        return True
    if bias is not None and abs(bias) >= rootcause.HIGH_BIAS:
        return True
    return ts is not None and abs(ts) >= rootcause.TS_LIMIT


def _entity(ctx: PlanningContext, sid: str, cmp: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    a = _attrs(ctx)
    r = a.loc[sid] if sid in a.index else None
    ent: dict[str, Any] = {"cmp": cmp, "series_id": sid}
    if r is not None:
        for d in ("region", "channel", "customer", "category", "brand", "sku"):
            ent[d] = r[d]
    ent.update(extra or {})
    return ent


def _path(filters: dict[str, Any]) -> dict[str, str]:
    return {p["dim"]: p["member"] for p in common.node_path(filters)}


# ======================================================================================== summary
def _kpis(cmp: str, m: dict[str, Any], cause1: dict[str, Any] | None, fva: dict[str, Any] | None) -> list[dict]:
    w, b = m["wmape"], m["bias"]
    bclass = bias_class(b) if b is not None else None
    kpis: list[dict[str, Any]] = [
        {
            "id": "accuracy",
            "label": KPI_LABEL["accuracy_cs" if cmp == "ac_cs" else "accuracy"],
            "value": m["accuracy"],
            "format": "percent",
            "hint": f"WMAPE {ptbr.pct(w, 1)} · em unidades" if w is not None else None,
        },
        {
            "id": "bias",
            "label": KPI_LABEL["bias"],
            "value": b,
            "format": "percent_signed",
            "delta": ptbr.BIAS_CLASS[bclass] if bclass else None,
            "delta_tone": "neutral" if bclass in (None, "Balanced") else "bad",
            "hint": "positivo = superestimou",
        },
        {
            "id": "abs_error",
            "label": KPI_LABEL["abs_error"],
            "value": m["abs_error"],
            "format": "currency",
            "hint": (
                f"{ptbr.pct(m['systematic_share'], 0)} sistemático" if m["systematic_share"] is not None else None
            ),
        },
    ]
    if cmp == "ac_cs":
        f = fva or {}
        ws, wc = f.get("statistical_wmape"), f.get("consensus_wmape")
        kpis.append(
            {
                "id": "fva",
                "label": KPI_LABEL["fva"],
                "value": f.get("fva_pp"),
                "format": "pp",
                "delta_tone": "neutral",
                "hint": f"estatístico {ptbr.pct(ws, 1)} → consenso {ptbr.pct(wc, 1)}" if ws is not None else None,
            }
        )
    else:
        kpis.append(
            {
                "id": "top_cause",
                "label": KPI_LABEL["top_cause"],
                "value": cause1["share"] if cause1 else None,
                "format": "text",
                "text": cause1["label"] if cause1 else "—",
                "hint": f"{ptbr.pct(cause1['share'], 0)} do erro" if cause1 else "sem erro no período",
            }
        )
    return kpis


def _fva(cells: pd.DataFrame) -> dict[str, Any]:
    """Statistical vs consensus WMAPE on the same cells (ac_cs)."""
    a = float(cells["actual"].sum()) if len(cells) else 0.0
    if a <= 0:
        return {"statistical_wmape": None, "consensus_wmape": None, "fva_pp": None}
    ws = float(cells["e_stat"].abs().sum() / a)
    wc = float(cells["e"].abs().sum() / a)
    return {"statistical_wmape": ws, "consensus_wmape": wc, "fva_pp": ws - wc}


def _headline_facts(node: str, per: common.Period, cmp: str, m: dict, cause1: dict | None) -> dict[str, Any]:
    return {
        "node": node,
        "period_phrase": common.period_phrase(per),
        "period_label": per.label,
        "wmape": m["wmape"],
        "abs_error": m["abs_error"],
        "bias": m["bias"],
        "cause1": cause1["label"] if cause1 else None,
        "cause1_share": cause1["share"] if cause1 else None,
        "consensus": cmp == "ac_cs",
    }


def _levels(ctx: PlanningContext, filters: dict[str, Any], n_series: int) -> list[dict[str, Any]]:
    """'Agrupar por' options of the forecast lens (same rules and texts as the plan lens)."""
    return common.level_options("ac_fc", filters, n_series)


def _next_level(filters: dict[str, Any], level: str) -> str | None:
    return common.level_after(filters, level)


def _notices(ctx: PlanningContext, per: common.Period, ids: pd.Index, cells_all: pd.DataFrame) -> list[str]:
    lag = common.lag_label(common.run_params(ctx)["fold_horizon"])
    out = [NOTE_OUT_OF_SAMPLE.format(lag=lag)]
    bt = common.backtest_months(ctx)
    if len(per.months.intersection(bt)) < MIN_MONTHS:
        out.append(NOTE_FEW_MONTHS)
    missing = len(ids) - int(cells_all["series_id"].nunique())
    if missing > 0:
        out.append(NOTE_COVERAGE.format(n=missing, m=len(ids)))
    return out


def _empty_summary(ctx, filters, cmp, per, ids, level, reason) -> dict[str, Any]:
    return clean(
        {
            "available": False,
            "reason": reason,
            "cmp": cmp,
            "lens": "forecast",
            "measure": "revenue",
            "period": _period_json(per),
            "periods": common.period_options(ctx, cmp),
            "comparisons": comparisons(ctx),
            "node": {"label": common.node_label(filters), "path": common.node_path(filters), "n_series": len(ids)},
            "headline": "",
            "notices": [],
            "kpis": [],
            "breakdown": {
                "level": level,
                "level_label": common.LEVEL_LABEL.get(level, level),
                "next_level": _next_level(filters, level),
                "levels": _levels(ctx, filters, len(ids)),
                "rows": [],
                "others": None,
                "n_members": 0,
            },
            "concentration": None,
        }
    )


def _concentration(labels: list[str], values: list[float]) -> dict[str, Any] | None:
    """Smallest k with cumulative share ≥ 50% (clamped 1..3) over members sorted by value desc."""
    total = float(sum(values))
    if total <= 0:
        return None
    cum, n_top = 0.0, 0
    for i, v in enumerate(values, start=1):
        cum += v / total
        n_top = i
        if cum >= CONC_SHARE - 1e-12 or i >= CONC_MAX:
            break
    share = float(sum(values[:n_top]) / total)
    return {"n_top": n_top, "share": share, "members": labels[:n_top], "n_members": len(values)}


def summary(
    ctx: PlanningContext,
    filters: dict[str, Any],
    cmp: str,
    period: str | None,
    measure: str,
    level: str | None,
    limit: int = 12,
) -> dict[str, Any]:
    """DeviationSummary of the forecast lens (spec §4.3.3)."""
    per, ids, _, _ = _scope(ctx, filters, cmp, period)
    level = level or common.next_level(filters)
    reason = _unavailable_reason(ctx, cmp)
    if reason is None and len(ids) == 0:
        reason = MSG_EMPTY_NODE
    cells_all = error_cells(ctx, cmp, ids, common.backtest_months(ctx)) if reason is None else None
    if reason is None and cells_all.empty:
        reason = MSG_NO_BACKTEST
    if reason is not None:
        return _empty_summary(ctx, filters, cmp, per, ids, level, reason)

    cells = cells_all[cells_all["date"].isin(per.months)]
    m = node_metrics(cells)
    causes = cause_rows(cells)
    cause1 = top_cause(causes)
    fva = _fva(cells) if cmp == "ac_cs" else None
    node = common.node_label(filters)

    # ---- breakdown
    st = _series_table(ctx, cells)
    rev_share = _rev_share(ctx)
    st["member"] = _member_of(ctx, st["series_id"], level)
    st["abs_sys"] = st["E"].abs()
    gm = st.groupby("member")
    grp = gm[["actual_units", "abs_e", "net_e", "actual", "forecast", "AE", "E", "abs_sys"]].sum()
    grp = grp.rename(columns={"abs_sys": "systematic"})
    grp["n_series"] = gm.size()
    cm = cells.assign(member=_member_of(ctx, cells["series_id"], level))
    by_cause = cm.groupby(["member", "cause"])["AE"].sum().reset_index()
    order = {c: i for i, c in enumerate(rootcause.CAUSES)}
    by_cause["prio"] = by_cause["cause"].map(order)
    best = (
        by_cause.sort_values(["member", "AE", "prio"], ascending=[True, False, True])
        .drop_duplicates("member")
        .set_index("member")
    )
    grp = grp.sort_values("AE", ascending=False, kind="mergesort")
    total_ae = float(grp["AE"].sum())
    st_idx = st.set_index("series_id")
    rows: list[dict[str, Any]] = []
    cum = 0.0
    for key, r in grp.iterrows():
        a = float(r["actual_units"])
        w = float(r["abs_e"]) / a if a > 0 else None
        b = float(r["net_e"]) / a if a > 0 else None
        ae = float(r["AE"])
        share = ae / total_ae if total_ae > 0 else 0.0
        cum += share
        sysv = min(float(r["systematic"]), ae)
        tc = None
        if key in best.index and ae > 0:
            code = best.at[key, "cause"]
            tc = {**rootcause.cause_tag(code), "share": float(best.at[key, "AE"]) / ae}
            tc.pop("group_label", None)
        if level == "series":
            ts = float(st_idx.at[key, "ts"]) if key in st_idx.index else None
            exc = _is_exception(w, b, ts, float(rev_share.get(key, 0.0)))
        else:
            exc = (w is not None and w >= rootcause.HIGH_ERROR) or (b is not None and abs(b) >= rootcause.HIGH_BIAS)
        row = {
            "key": str(key),
            "label": member_label(ctx, level, str(key)),
            "actual": float(r["actual"]),
            "forecast": float(r["forecast"]),
            "abs_error": ae,
            "net_error": float(r["E"]),
            "wmape": w,
            "bias": b,
            "bias_class": bias_class(b) if b is not None else None,
            "systematic": sysv,
            "noise": max(0.0, ae - sysv),
            "share": share,
            "cum_share": min(cum, 1.0),
            "top_cause": tc,
            "is_exception": bool(exc),
            "n_series": int(r["n_series"]),
            "drillable": bool(level in common.DIMS and int(r["n_series"]) > 1),
        }
        if level == "series":
            row["series_id"] = str(key)
        rows.append(row)
    kept, rest = rows[: max(0, int(limit))], rows[max(0, int(limit)) :]
    others = {"n": len(rest), "value": float(sum(x["abs_error"] for x in rest))} if rest else None
    concentration = _concentration([x["label"] for x in rows], [x["abs_error"] for x in rows])

    return clean(
        {
            "available": True,
            "cmp": cmp,
            "lens": "forecast",
            "measure": "revenue",
            "period": _period_json(per),
            "periods": common.period_options(ctx, cmp),
            "comparisons": comparisons(ctx),
            "node": {"label": node, "path": common.node_path(filters), "n_series": len(ids)},
            "headline": narrative.summary_headline(_headline_facts(node, per, cmp, m, cause1), cmp),
            "notices": _notices(ctx, per, ids, cells_all),
            "kpis": _kpis(cmp, m, cause1, fva),
            "breakdown": {
                "level": level,
                "level_label": common.LEVEL_LABEL.get(level, level),
                "next_level": _next_level(filters, level),
                "levels": _levels(ctx, filters, len(ids)),
                "rows": kept,
                "others": others,
                "n_members": len(rows),
            },
            "concentration": concentration,
        }
    )


# ======================================================================================== focus
def _monthly(cells: pd.DataFrame) -> list[dict[str, Any]]:
    """MonthlyErrorRow[] (R$ at the realized price; WMAPE in units)."""
    out = []
    for d, g in cells.groupby("date"):
        a = float(g["actual"].sum())
        out.append(
            {
                "date": d,
                "actual": float(g["actual_rev"].sum()),
                "forecast": float(g["forecast_rev"].sum()),
                "error": float(g["E"].sum()),
                "abs_error": float(g["AE"].sum()),
                "wmape": float(g["e"].abs().sum() / a) if a > 0 else None,
            }
        )
    return out


def _target_series(cells: pd.DataFrame, code: str) -> pd.Series | None:
    """Largest cell of a cause (the series/month the action buttons point to)."""
    sub = cells[cells["cause"] == code]
    if sub.empty:
        return None
    sid = sub.groupby("series_id")["AE"].sum().idxmax()
    return sub[sub["series_id"] == sid].sort_values("AE", ascending=False).iloc[0]


def _cause_actions(
    ctx: PlanningContext,
    cmp: str,
    cells: pd.DataFrame,
    code: str | None,
    ask: dict[str, Any],
    single_series: bool,
) -> list[dict[str, Any]]:
    """actions_for(top cause) pointed at the series that best exemplifies the cause in ``cells``."""
    if not code:
        return rootcause.actions_for("nao_explicado", ask, ctx)
    cell = _target_series(cells, code)
    if cell is None:
        return rootcause.actions_for(code, ask, ctx)
    dist = cell["distribution"] - cell["distribution_origin"]
    ent = _entity(
        ctx,
        str(cell["series_id"]),
        cmp,
        {
            **ask,
            "date": cell["date"],
            "cause_label": rootcause.CAUSES[code][0],
            "dist_change": None if pd.isna(dist) else float(dist),
        },
    )
    acts = rootcause.actions_for(code, ent, ctx)
    if not single_series:
        target = f"{ent.get('customer')} · {ent.get('sku')}"
        for a in acts:
            if a["kind"] in ("create_override", "open_series", "open_workspace") or (
                a["kind"] == "simulate" and code == "distribuicao"
            ):
                a["label"] = f"{a['label']} · {target}"
    return acts


def focus(
    ctx: PlanningContext,
    filters: dict[str, Any],
    cmp: str,
    period: str | None,
    measure: str,
    focus_level: str | None = None,
    focus: str | None = None,
) -> dict[str, Any]:
    """DeviationFocus of the forecast lens: causes, systematic/noise split, error by champion model,
    monthly error over the whole backtest window, diagnosis and actions (spec §4.3.3)."""
    per, ids, lv, member = _scope(ctx, filters, cmp, period, focus_level, focus)
    node = common.node_label(filters)
    label = member_label(ctx, lv, member) if member else node
    base: dict[str, Any] = {
        "available": True,
        "cmp": cmp,
        "lens": "forecast",
        "measure": "revenue",
        "period": _period_json(per),
        "focus": {"level": lv, "member": member, "label": label},
        "headline": "",
        "bridge": None,
        "drivers": None,
        "causes": None,
        "split": None,
        "by_model": None,
        "fva": None,
        "monthly": [],
        "quarters": None,
        "diagnosis": [],
        "actions": [],
    }
    reason = _unavailable_reason(ctx, cmp)
    if reason is None and len(ids) == 0:
        reason = MSG_EMPTY_NODE
    cells_all = error_cells(ctx, cmp, ids, common.backtest_months(ctx)) if reason is None else None
    if reason is None and cells_all.empty:
        reason = MSG_NO_BACKTEST
    if reason is not None:
        return clean({**base, "available": False, "reason": reason})

    cells = cells_all[cells_all["date"].isin(per.months)]
    m = node_metrics(cells)
    causes = cause_rows(cells)
    cause1 = top_cause(causes)
    fva = _fva(cells) if cmp == "ac_cs" else None
    facts = _headline_facts(node, per, cmp, m, cause1)
    if member:
        facts["member"] = label
    headline = (narrative.focus_headline if member else narrative.summary_headline)(facts, cmp)
    lead = lead_controllable(causes, cause1)
    diagnosis = narrative.forecast_diagnosis(
        {
            "systematic_share": m["systematic_share"],
            "cause1": cause1["label"] if cause1 else None,
            "cause1_abs_error": cause1["abs_error"] if cause1 else None,
            "cause1_n_cells": cause1["n_cells"] if cause1 else None,
            "cause1_direction": cause1["direction"] if cause1 else None,
            "fva_pp": (fva or {}).get("fva_pp"),
            "lead_controllable": lead["label"] if lead else None,
            "lead_controllable_abs_error": lead["abs_error"] if lead else None,
            "lead_controllable_share": lead["share"] if lead else None,
        },
        cmp,
    )
    path = _path(filters)
    if member and lv in common.DIMS:
        path[lv] = member
    ask = {"cmp": cmp, "level": lv, "member": member, "bias": m["bias"], "path": path}
    if lv == "series" and member:
        ent = _entity(ctx, member, cmp)
        path.update({d: ent[d] for d in ("customer", "sku") if ent.get(d)})
        ask.update({k: v for k, v in ent.items() if k != "cmp"})
    action_cause = lead or cause1
    actions = _cause_actions(ctx, cmp, cells, action_cause["code"] if action_cause else None, ask, lv == "series")
    return clean(
        {
            **base,
            "headline": headline,
            "causes": causes,
            "split": {
                "systematic": m["systematic"],
                "noise": m["noise"],
                "systematic_share": m["systematic_share"],
            },
            "by_model": by_model(ctx, cells),
            "fva": fva,
            "monthly": _monthly(cells_all),
            "diagnosis": diagnosis,
            "actions": actions,
        }
    )


# ======================================================================================== exceptions
def _exception_row(ctx: PlanningContext, cmp: str, r: pd.Series) -> dict[str, Any]:
    sid = str(r["series_id"])
    a = _attrs(ctx)
    s = a.loc[sid] if sid in a.index else pd.Series(dtype=object)
    code = r["top_cause"] if isinstance(r["top_cause"], str) else None
    mes = ptbr.month_label(r["top_date"]) if code and not pd.isna(r["top_date"]) else ""
    dist = r.get("top_dist_change")
    ent = _entity(
        ctx,
        sid,
        cmp,
        {
            "level": "series",
            "bias": r["bias"],
            "date": r["top_date"] if code else None,
            "cause_label": rootcause.CAUSES[code][0] if code else None,
            "dist_change": None if dist is None or pd.isna(dist) else float(dist),
        },
    )
    tag = {"code": code, "label": rootcause.CAUSES[code][0]} if code else None
    return {
        "series_id": sid,
        "label": _series_label(ctx, sid),
        "customer": s.get("customer"),
        "sku": s.get("sku"),
        "product": s.get("product"),
        "region": s.get("region"),
        "channel": s.get("channel"),
        "category": s.get("category"),
        "impact": float(r["AE"]),
        "abs_error": float(r["AE"]),
        "wmape": r["wmape"],
        "bias": r["bias"],
        "tracking_signal": float(r["ts"]),
        "top_cause": {**tag, "group": rootcause.CAUSES[code][1]} if tag else None,
        "confidence": s.get("confidence"),
        "champion": s.get("champion"),
        "series_type_label": ptbr.series_type(s.get("series_type")) if s.get("series_type") else None,
        "tags": [tag] if tag else [],
        "recommended_action": rootcause.recommended_action(code or "nao_explicado", cause=True, mes=mes),
        "actions": rootcause.menu_actions(code, ent, ctx),
    }


def exceptions(
    ctx: PlanningContext,
    filters: dict[str, Any],
    cmp: str,
    period: str | None,
    measure: str,
    focus_level: str | None = None,
    focus: str | None = None,
    cause: str | None = None,
    limit: int = 15,
    offset: int = 0,
) -> dict[str, Any]:
    """Series to act on first (spec §4.3.3 "Forecast exception"): WMAPE ≥ 35% (with ≥ 0,1% of the
    company consensus revenue) or |bias| ≥ 15% or |TS| ≥ 4,5. Impact = AE of the series in the period;
    sorted by impact.

    ``cause`` (a click on a CauseBars bar, or the report's "causa" link) lists the series of the node whose
    top cause is that cause, sorted by impact, whether or not they pass the exception rule: the exception
    rule alone would leave the table empty for the inherent causes (a series whose error is mostly
    "variação normal" is never an exception) and would hide most series of a controllable cause (on the
    demo, 9 of the 36 series led by "promoção não antecipada")."""
    if cause not in (None, "") and cause not in rootcause.CAUSES:
        raise common.DeviationError(MSG_INVALID_CAUSE)
    per, ids, _, _ = _scope(ctx, filters, cmp, period, focus_level, focus)
    if _unavailable_reason(ctx, cmp) is not None or len(ids) == 0:
        return {"total": 0, "rows": []}
    cells = error_cells(ctx, cmp, ids, per.months)
    st = _series_table(ctx, cells)
    if st.empty:
        return {"total": 0, "rows": []}
    rev_share = _rev_share(ctx)
    a = st["actual_units"].astype(float)
    st["wmape"] = (st["abs_e"] / a).where(a > 0)
    st["bias"] = (st["net_e"] / a).where(a > 0)
    st["exc"] = [
        _is_exception(
            None if pd.isna(w) else float(w),
            None if pd.isna(b) else float(b),
            float(t),
            float(rev_share.get(sid, 0.0)),
        )
        for w, b, t, sid in zip(st["wmape"], st["bias"], st["ts"], st["series_id"], strict=True)
    ]
    sel = st[st["top_cause"] == cause] if cause else st[st["exc"]]
    sel = sel.sort_values(["AE", "series_id"], ascending=[False, True])
    page = sel.iloc[max(0, int(offset)) : max(0, int(offset)) + max(0, int(limit))]
    rows = [_exception_row(ctx, cmp, r) for _, r in page.iterrows()]
    return clean({"total": len(sel), "rows": rows})


# ======================================================================================== series
def _future_overrides(ctx: PlanningContext, customer: str, sku: str) -> list[dict[str, Any]]:
    ov = ctx.overrides
    if ov is None or ov.empty:
        return []
    cust_ok = ov["customer"].isna() | (ov["customer"].fillna("") == "") | (ov["customer"] == customer)
    sku_ok = ov["sku"].isna() | (ov["sku"].fillna("") == "") | (ov["sku"] == sku)
    sel = ov[cust_ok & sku_ok & ov["date"].isin(ctx.future_dates)].sort_values("date")
    return [
        {
            "date": r["date"],
            "event_type": ptbr.label(ptbr.EVENT_TYPE, r["event_type"]),
            "uplift_pct": float(r["uplift_pct"]),
            "comment": r["comment"] if isinstance(r["comment"], str) and r["comment"] else None,
        }
        for _, r in sel.iterrows()
    ]


def series(ctx: PlanningContext, series_id: str, cmp: str, period: str | None, measure: str) -> dict[str, Any]:
    """DeviationSeries of the forecast lens ("Ficha da série"): summary over the period, evidence for
    every backtest month (R$ at the realized price; error % = e/A), recommended action and actions."""
    s = common.require_series(ctx, series_id)
    per = common.parse_period(ctx, cmp, period)
    customer, sku = str(s["customer"]), str(s["sku"])
    header = {
        "customer": customer,
        "sku": sku,
        "product": s.get("product"),
        "region": s.get("region"),
        "channel": s.get("channel"),
        "category": s.get("category"),
        "series_type_label": ptbr.series_type(s.get("series_type")),
        "confidence": s.get("confidence"),
        "champion": s.get("champion"),
        "challenger": s.get("challenger"),
    }
    tl = records(timeline(ctx, {"customer": [customer], "sku": [sku]}, "revenue", TIMELINE_MONTHS))
    out: dict[str, Any] = {
        "available": True,
        "series_id": series_id,
        "label": _series_label(ctx, series_id),
        "header": header,
        "summary": {"reference": None, "compared": None, "variance": None, "variance_pct": None},
        "timeline": tl,
        "evidence": None,
        "months": None,
        "effects": None,
        "tags": [],
        "recommended_action": rootcause.recommended_action("nao_explicado", cause=True),
        "actions": [],
        "future_overrides": _future_overrides(ctx, customer, sku),
    }
    reason = _unavailable_reason(ctx, cmp)
    cells_all = error_cells(ctx, cmp, pd.Index([series_id]), common.backtest_months(ctx)) if reason is None else None
    if reason is None and cells_all.empty:
        reason = MSG_NO_BACKTEST
    if reason is not None:
        return clean({**out, "available": False, "reason": reason})

    cells = cells_all[cells_all["date"].isin(per.months)]
    m = node_metrics(cells)
    st = _series_table(ctx, cells)
    code = None
    top_date, dist = None, None
    if not st.empty and isinstance(st.iloc[0]["top_cause"], str):
        code = st.iloc[0]["top_cause"]
        top_date = st.iloc[0]["top_date"]
        dist = st.iloc[0]["top_dist_change"]
    evidence = []
    for r in cells_all.to_dict("records"):
        a = float(r["actual"])
        evidence.append(
            {
                "date": r["date"],
                "horizon_step": int(r["horizon_step"]),
                "actual": float(r["actual_rev"]),
                "forecast": float(r["forecast_rev"]),
                "error": float(r["E"]),
                "error_pct": float(r["e"]) / a if a > 0 else None,
                "cause": {k: v for k, v in rootcause.cause_tag(r["cause"]).items() if k != "group_label"},
                "evidence": rootcause.cell_evidence(r),
            }
        )
    mes = ptbr.month_label(top_date) if code and top_date is not None and not pd.isna(top_date) else ""
    ent = _entity(
        ctx,
        series_id,
        cmp,
        {
            "level": "series",
            "bias": m["bias"],
            "date": top_date if code else None,
            "cause_label": rootcause.CAUSES[code][0] if code else None,
            "dist_change": None if dist is None or pd.isna(dist) else float(dist),
        },
    )
    return clean(
        {
            **out,
            "summary": {
                "reference": m["actual"],
                "compared": m["forecast"],
                "variance": m["net_error"],
                "variance_pct": m["bias"],
            },
            "evidence": evidence,
            "tags": [{"code": code, "label": rootcause.CAUSES[code][0]}] if code else [],
            "recommended_action": rootcause.recommended_action(code or "nao_explicado", cause=True, mes=mes),
            "actions": rootcause.menu_actions(code, ent, ctx, drawer=True),
        }
    )
