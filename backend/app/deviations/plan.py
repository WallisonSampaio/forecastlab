"""Plan lens of the deep dive: fc_pl, fc_tg and ac_pl (spec §4.2.2–§4.2.6, §4.3.3).

``service`` dispatches here for the plan comparisons; the four functions return the JSON shapes
``DeviationSummary``, ``DeviationFocus``, ``DeviationExceptions`` and ``DeviationSeries``
(``frontend/src/types/deviations.ts``).

Arguments: ``filters`` as produced by ``api.deps.filters_dep``; ``period`` is the raw period code
(None = comparison default, parsed with ``common.parse_period``); ``measure`` is 'revenue' | 'units';
``level`` / ``focus_level`` are already validated by ``service`` (None = ``common.next_level``).

Definitions (all on the full grid ids × M, M = period months ∩ plan months):

* X = Σ compared side (consensus at the forecast price for fc_*, realized for ac_pl), P = Σ reference
  (budget; target for fc_tg), V = X − P, V% = V/P.
* Price / volume / mix / events bridge, exact and additive over any partition of cells (§4.2.3):
  vol = (Q_stat − Q_ref)·P̄_N, mix = (Q_stat − Q_ref)·(p_ref − P̄_N) + res, price = Q_stat·(p_x − p_ref),
  events = Q_inc·p_x. fc_tg computes the effects against the budget and adds the commercial
  challenge step (Meta − Orçamento). Members inside a breakdown use the parent node's P̄.
* Probability of reaching the reference (fc_*, §4.2.5) with the consensus band of ``assess``.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from app.services import datasets, ptbr
from app.services.context import RHO, Z90, PlanningContext, filter_ids, records, timeline
from app.sop.feasibility import CLASSES, assess, classify
from app.sop.feasibility import _levers as feasibility_levers

from . import common, narrative, rootcause
from .cells import plan_cells

FC_CMPS = ("fc_pl", "fc_tg")
ATTR_COLS = ["customer", "sku", "product", "region", "channel", "category", "brand", "series_type"]
KEY = ["series_id", "date"]

# Exception thresholds (spec §4.3.3 "Plan exception" and "Breakdown-row is_exception").
MIN_ABS_VARIANCE = {"revenue": 10_000.0, "units": 1_000.0}
ROW_SHARE_OF_P = 0.01
SERIES_SHARE_OF_P = 0.001
EXC_VPCT = 0.05
EXC_PROB = 0.70
ALIGNED_VPCT = 0.005  # |V%| below this reads "alinhado"
RECURRENT_VPCT = 0.05  # §4.2.2 recurrence: same-direction realized deviation of at least 5%
PARETO_SHARE = 0.5
PARETO_MAX = 3

SUM_COLS = [
    "x",
    "ref",
    "ly",
    "b",
    "tg",
    "x_rev",
    "r_ref",
    "xk",
    "sk",
    "sk2",
    "x_rev_decline",
    "volume",
    "mix",
    "price",
    "events",
]

EFFECT_SHORT = {
    "volume": "Volume",
    "mix": "Mix",
    "price": "Preço",
    "events": "Eventos",
    "challenge": "Desafio comercial",
}

BRIDGE_NOTE = "Volume valorizado ao preço médio orçado do recorte; mix no nível Cliente × SKU × mês."
BRIDGE_NOTE_UNITS = "Em unidades não há efeito preço/mix."
HELP = {
    "reference_pl": "Orçamento do recorte no período.",
    "reference_tg": "Meta de vendas do recorte no período.",
    "challenge": "Desafio comercial: quanto a meta excede o orçamento (Meta − Orçamento).",
    "budget_subtotal": "Orçamento do recorte no período: a meta menos o desafio comercial.",
    "volume": "Diferença de unidades frente ao orçado, valorizada ao preço médio orçado do recorte.",
    "volume_units": "Diferença de unidades frente ao orçado.",
    "mix": "Composição Cliente × SKU × mês: vender mais (ou menos) itens de preço orçado acima da média.",
    "price_fc": "Preço atual de cada série frente ao preço implícito no orçamento.",
    "price_ac": "Preço realizado de cada série frente ao preço implícito no orçamento.",
    "events": "Eventos comerciais cadastrados: ajustes do consenso sobre o forecast estatístico.",
    "compared_fc": "Consenso = forecast estatístico + eventos comerciais.",
    "compared_ac": "Venda realizada no período.",
}
ASK_AI_LABEL = "Perguntar à IA"


# ================================================================================== formatting helpers
def _f(v: Any) -> float | None:
    """Finite float or None."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _fmt(v: float | None, measure: str, signed: bool = False) -> str:
    """'R$ 4,09 mi' | '12.345 unidades'; ``signed`` adds '+' to positive values."""
    if _f(v) is None:
        return ptbr.NA
    s = ptbr.money(v) if measure == "revenue" else ptbr.units(v)
    return f"+{s}" if signed and float(v) > 0 else s


def _ratio(a: float, b: float) -> float | None:
    return a / b if b else None


# ================================================================================== scope
@dataclass
class _Scope:
    ctx: PlanningContext
    cmp: str
    measure: str
    period: common.Period
    filters: dict[str, Any]
    ids: pd.Index
    months: pd.DatetimeIndex
    cells: pd.DataFrame
    notices: list[str] = field(default_factory=list)
    reason: str | None = None

    @property
    def available(self) -> bool:
        return self.reason is None


def _scope(ctx: PlanningContext, filters: dict[str, Any], cmp: str, period: common.Period, measure: str) -> _Scope:
    ids = filter_ids(ctx, filters)
    notices: list[str] = []
    reason = None
    pm = common.plan_months(ctx)
    months = period.months[period.months.isin(pm)] if len(pm) else pd.DatetimeIndex([])
    if not ctx.has_run:
        reason = common.MSG_NO_RUN
    elif len(pm) == 0:
        reason = common.MSG_NO_PLAN
    elif len(months) == 0:
        reason = common.MSG_NO_PLAN_PERIOD
    elif len(ids) == 0:
        reason = common.MSG_NO_SERIES
    if reason is None:
        if common.plan_derived(ctx):
            notices.append(common.NOTICE_DERIVED_PLAN)
        if len(months) < len(period.months):
            notices.append(common.NOTICE_PARTIAL_PLAN.format(n=len(months), m=len(period.months)))
    cells = _cells(ctx, cmp, measure, ids, months) if reason is None else pd.DataFrame()
    return _Scope(ctx, cmp, measure, period, filters, ids, pd.DatetimeIndex(months), cells, notices, reason)


def _override_cells(ctx: PlanningContext, cmp: str) -> pd.DataFrame:
    """Company-wide override × cell rows over the comparison window: series_id, date, oid, event_type, u.

    fc_*: the future commercial overrides (``ctx.overrides``, uplift_pct); ac_pl: the historical
    adjustments (adjustment_pct). Matching follows ``context._apply_overrides``: same date, a blank
    customer or SKU means "all". Event types are normalised to pt-BR (legacy rows are in English).
    """

    def build() -> pd.DataFrame:
        cols = ["series_id", "date", "oid", "event_type", "u"]
        if cmp == "ac_pl":
            ov = datasets.get_historical_overrides(ctx.version)
            value = "adjustment_pct"
        else:
            ov = ctx.overrides
            value = "uplift_pct"
        if ov is None or ov.empty:
            return pd.DataFrame(columns=cols)
        window = pd.DatetimeIndex(common.window(ctx, cmp)[0]).astype("datetime64[ns]")
        o = pd.DataFrame(
            {
                "customer": ov["customer"].astype(object).where(ov["customer"].notna(), "").astype(str),
                "sku": ov["sku"].astype(object).where(ov["sku"].notna(), "").astype(str),
                "date": pd.to_datetime(ov["date"]).dt.to_period("M").dt.to_timestamp().astype("datetime64[ns]"),
                "oid": (
                    ov["override_id"].astype(str)
                    if "override_id" in ov
                    else pd.Series([f"H{i}" for i in range(len(ov))], index=ov.index)
                ),
                "event_type": [str(ptbr.label(ptbr.EVENT_TYPE, v) or ptbr.NA) for v in ov["event_type"]],
                "u": pd.to_numeric(ov[value], errors="coerce").fillna(0.0).astype(float),
            }
        )
        o = o[o["date"].isin(window)]
        s = ctx.series[["series_id", "customer", "sku"]].astype(object)
        has_c, has_s = o["customer"] != "", o["sku"] != ""
        parts = [
            o[has_c & has_s].merge(s, on=["customer", "sku"]),
            o[has_c & ~has_s].drop(columns="sku").merge(s, on="customer"),
            o[~has_c & has_s].drop(columns="customer").merge(s, on="sku"),
            o[~has_c & ~has_s].drop(columns=["customer", "sku"]).merge(s, how="cross"),
        ]
        parts = [p[cols] for p in parts if not p.empty]
        if not parts:
            return pd.DataFrame(columns=cols)
        return pd.concat(parts, ignore_index=True)

    return common.cached(ctx, "plan.override_cells", cmp, build=build)


def _enrich(ctx: PlanningContext, cmp: str, measure: str, c: pd.DataFrame) -> pd.DataFrame:
    """Adds attributes, an integer series code and the measure columns used by every aggregate."""
    c = c.copy()
    s = ctx.series.reset_index(drop=True)
    pos = pd.Series(np.arange(len(s)), index=pd.Index(s["series_id"], dtype=object))
    c["sidx"] = c["series_id"].map(pos).fillna(-1).astype(np.int64).to_numpy()
    attrs = s.set_index("series_id")
    for col in ATTR_COLS:
        c[col] = c["series_id"].map(attrs[col])
    rev = measure == "revenue"
    c["x"] = c["x_rev"] if rev else c["x_units"]
    c["ref"] = c["r_ref"] if rev else c["q_ref"]
    c["ly"] = c["ly_rev"] if rev else c["ly_units"]
    c["b"] = c["budget_revenue"] if rev else c["budget_units"]
    c["tg"] = c["target_revenue"] if rev else c["target_units"]
    # Effects reference: the budget for fc_tg (bridge Meta → challenge → Orçamento → effects → Consenso).
    c["eq"] = c["budget_units"] if cmp == "fc_tg" else c["q_ref"]
    c["er"] = c["budget_revenue"] if cmp == "fc_tg" else c["r_ref"]
    if cmp in FC_CMPS:
        k = c["p_fc"] if rev else 1.0
        c["xk"] = c["q_stat"] * k
        c["sk"] = c["sigma"].fillna(0.0) * k
    else:
        c["xk"] = 0.0
        c["sk"] = 0.0
    c["sk2"] = c["sk"] ** 2
    decline = c["series_type"].isin(rootcause.DECLINE_TYPES)
    c["x_rev_decline"] = c["x_rev"].where(decline, 0.0)
    oc = _override_cells(ctx, cmp)
    struct = oc[oc["event_type"].isin(rootcause.STRUCT_EVENTS)] if not oc.empty else oc
    if struct.empty:
        c["struct"] = False
    else:
        hit = pd.MultiIndex.from_frame(struct[KEY].drop_duplicates())
        c["struct"] = pd.MultiIndex.from_frame(c[KEY]).isin(hit)
    # Categorical keys: slicing and grouping the cached frame stay cheap (group with observed=True).
    for col in ("series_id", *ATTR_COLS):
        c[col] = c[col].astype("category")
    return c


def _series_codes(ctx: PlanningContext, ids: pd.Index) -> np.ndarray:
    """Positions of ``ids`` in ``ctx.series`` (−1 for unknown ids)."""
    pos = common.cached(ctx, "plan.series_pos", build=lambda: {sid: i for i, sid in enumerate(ctx.series["series_id"])})
    return np.array([pos.get(sid, -1) for sid in ids], dtype=np.int64)


def _cells(ctx: PlanningContext, cmp: str, measure: str, ids: pd.Index, months: pd.DatetimeIndex) -> pd.DataFrame:
    """Enriched full-grid cells ids × months, sliced from the cached company-wide frame (§4.7)."""
    window = pd.DatetimeIndex(common.window(ctx, cmp)[0]).astype("datetime64[ns]")
    months = pd.DatetimeIndex(months).astype("datetime64[ns]")
    codes = _series_codes(ctx, pd.Index(ids))
    if not (months.isin(window).all() and (codes >= 0).all()):
        return _enrich(ctx, cmp, measure, plan_cells(ctx, cmp, ids, months))
    base = common.cached(
        ctx,
        "plan.enriched",
        cmp,
        measure,
        build=lambda: _enrich(
            ctx, cmp, measure, plan_cells(ctx, cmp, pd.Index(ctx.series["series_id"], dtype=object), window)
        ),
    )
    if len(np.unique(codes)) == len(ctx.series) and len(months) == len(window):
        return base
    mask = np.isin(base["sidx"].to_numpy(), codes) & np.isin(base["date"].to_numpy(), months.to_numpy())
    return base[mask].reset_index(drop=True)


def _pbar(c: pd.DataFrame) -> float:
    """P̄_N = Σ R_ref / Σ Q_ref over the node; fallback Σ X^r / Σ Q_cons; else 0."""
    q = float(c["eq"].sum())
    if q > 0:
        return float(c["er"].sum()) / q
    qc = float(c["q_cons"].sum())
    return float(c["x_rev"].sum()) / qc if qc > 0 else 0.0


def _with_effects(c: pd.DataFrame, pbar: float, measure: str) -> pd.DataFrame:
    """Cell effects (volume, mix, price, events) valued with the node's ``pbar`` (§4.2.3).

    Revenue: exact identity Σ effects = Σ X^r − Σ R_ref (fc_tg: against the budget). Units:
    volume = Q_stat − Q_ref, events = Q_inc, mix = price = NaN.
    """
    q_stat, eq, er, p_x, q_inc = (c[k].to_numpy(dtype=float) for k in ("q_stat", "eq", "er", "p_x", "q_inc"))
    if measure == "revenue":
        with np.errstate(divide="ignore", invalid="ignore"):
            p_ref = np.where(eq > 0, er / np.where(eq > 0, eq, 1.0), p_x)
        vol = (q_stat - eq) * pbar
        mix = (q_stat - eq) * (p_ref - pbar)
        price = q_stat * (p_x - p_ref)
        events = q_inc * p_x
        res = (c["x_rev"].to_numpy(dtype=float) - er) - (vol + mix + price + events)
        mix = mix + res
    else:
        vol = q_stat - eq
        mix = np.full(len(c), np.nan)
        price = np.full(len(c), np.nan)
        events = q_inc
    return c.assign(volume=vol, mix=mix, price=price, events=events)


def _group(df: pd.DataFrame, key: str | None) -> list[tuple[Any, dict[str, Any]]]:
    """[(member, sums + derived metrics)] by ``key`` (None = the whole node, member '__node__').

    Pure numpy (``bincount`` over factorised keys): the endpoints group the same cached frame many
    times per request. Cells whose key is missing are dropped, as ``groupby`` would.
    """
    cols = {c: df[c].to_numpy(dtype=float) for c in SUM_COLS}
    struct = df["struct"].to_numpy(dtype=bool)
    sidx = df["sidx"].to_numpy(dtype=np.int64)
    if key is None:
        members: list[Any] = ["__node__"]
        sums = {c: np.array([a.sum()]) for c, a in cols.items()}
        flags = np.array([bool(struct.any())])
        n_series = np.array([len(np.unique(sidx))])
    else:
        codes, uniques = pd.factorize(df[key], sort=False)
        keep = codes >= 0
        codes, n = codes[keep], len(uniques)
        members = [str(u) for u in uniques]
        sums = {c: np.bincount(codes, weights=a[keep], minlength=n) for c, a in cols.items()}
        flags = np.bincount(codes, weights=struct[keep].astype(float), minlength=n) > 0
        pairs = np.unique(np.stack([codes, sidx[keep]], axis=1), axis=0) if len(codes) else np.empty((0, 2), int)
        n_series = np.bincount(pairs[:, 0], minlength=n) if len(pairs) else np.zeros(n, dtype=int)
    arrays = _derive({**sums, "struct": flags, "n_series": n_series})
    return [(m, {k: a[i] for k, a in arrays.items()}) for i, m in enumerate(members)]


def _node_row(df: pd.DataFrame) -> dict[str, Any]:
    """Aggregate row of the whole frame."""
    return _group(df, None)[0][1]


def _derive(g: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Vectorised node metrics: V, V%, growth, σ_N, prob_hit and the consensus band (§4.2.5)."""
    x, ref, ly = g["x"], g["ref"], g["ly"]
    xk, sk, sk2 = g["xk"], g["sk"], g["sk2"]
    x_rev, x_rev_decline = g["x_rev"], g["x_rev_decline"]
    with np.errstate(divide="ignore", invalid="ignore"):
        v = x - ref
        vpct = np.where(ref != 0, v / np.where(ref != 0, ref, 1.0), np.nan)
        g_plan = np.where(ly != 0, ref / np.where(ly != 0, ly, 1.0) - 1, np.nan)
        g_fc = np.where(ly != 0, x / np.where(ly != 0, ly, 1.0) - 1, np.nan)
        raw = np.sqrt(np.maximum(0.0, (1 - RHO) * sk2 + RHO * sk**2))
        sigma_n = np.where(xk > 0, raw * (x / np.where(xk > 0, xk, 1.0)), 0.0)
        z = (ref - x) / np.where(sigma_n > 0, sigma_n, 1.0)
        prob = np.where(sigma_n > 0, 1 - norm.cdf(z), (x >= ref).astype(float))
        decline_share = np.where(x_rev > 0, x_rev_decline / np.where(x_rev > 0, x_rev, 1.0), 0.0)
    return {
        **g,
        "v": v,
        "vpct": vpct,
        "g_plan": g_plan,
        "g_fc": g_fc,
        "sigma_n": sigma_n,
        "prob": prob,
        "p_dir": np.where(v < 0, 1 - prob, prob),
        "p10": np.maximum(0.0, x - Z90 * sigma_n),
        "p90": x + Z90 * sigma_n,
        "decline_share": decline_share,
    }


def _facts(r: dict[str, Any], cmp: str, measure: str) -> dict[str, Any]:
    """Facts of one aggregate row (node, member or series) for tags, KPIs and sentences."""
    fc = cmp in FC_CMPS
    rev = measure == "revenue"
    effects = {
        "volume": _f(r["volume"]) or 0.0,
        "mix": (_f(r["mix"]) or 0.0) if rev else None,
        "price": (_f(r["price"]) or 0.0) if rev else None,
        "events": (_f(r["events"]) or 0.0) if fc else None,
    }
    return {
        "x": float(r["x"]),
        "p": float(r["ref"]),
        "variance": float(r["v"]),
        "variance_pct": _f(r["vpct"]),
        "ly": float(r["ly"]),
        "budget": float(r["b"]),
        "target": float(r["tg"]),
        "g_plan": _f(r["g_plan"]),
        "g_fc": _f(r["g_fc"]),
        "challenge": float(r["tg"] - r["b"]) if cmp == "fc_tg" else None,
        "effects": effects,
        "prob_hit": _f(r["prob"]) if fc else None,
        "p_dir": _f(r["p_dir"]) if fc else None,
        "sigma_n": _f(r["sigma_n"]) if fc else None,
        "p10": _f(r["p10"]) if fc else None,
        "p90": _f(r["p90"]) if fc else None,
        "decline_share": _f(r["decline_share"]) or 0.0,
        "structural_event": bool(r["struct"]),
        "n_series": int(r["n_series"]),
        "x_rev": float(r["x_rev"]),
        "r_ref": float(r["r_ref"]),
    }


def _tags(facts: dict[str, Any], cmp: str) -> list[dict[str, str]]:
    return list(rootcause.plan_tags(facts, cmp) or [])[:2]


def _primary(tags: list[dict[str, str]]) -> str:
    return tags[0]["code"] if tags else "volume"


def _passes(facts: dict[str, Any], primary: str, min_abs: float) -> bool:
    """Shared exception test: size, then (|V%| ≥ 5% or p_dir ≥ 0,70), and not 'Dentro da incerteza'."""
    v = facts["variance"]
    if abs(v) < min_abs or v == 0:
        return False
    vpct = facts["variance_pct"]
    big = vpct is None or abs(vpct) >= EXC_VPCT
    likely = facts["p_dir"] is not None and facts["p_dir"] >= EXC_PROB
    return (big or likely) and primary != "incerteza"


def _recurrent(variance: float, rv: float | None) -> bool:
    if rv is None:
        return False
    return (variance < 0 and rv <= -RECURRENT_VPCT) or (variance > 0 and rv >= RECURRENT_VPCT)


# ================================================================================== recurrence
def _realized(ctx: PlanningContext, ids: pd.Index, key: str | None) -> dict[Any, float | None]:
    """ac_pl / U12M / revenue V% by ``key`` (None = node, under '__node__'); None where P = 0."""
    pm = common.plan_months(ctx)
    ltm = pd.DatetimeIndex(ctx.ltm_dates)
    months = ltm[ltm.isin(pm)]
    if not len(months) or not len(ids):
        return {}
    c = _cells(ctx, "ac_pl", "revenue", ids, months)
    if key is None:
        sums = {"__node__": (float(c["x_rev"].sum()), float(c["r_ref"].sum()))}
    else:
        g = c.groupby(key, sort=False, observed=True)[["x_rev", "r_ref"]].sum()
        sums = {k: (float(a), float(b)) for k, a, b in zip(g.index, g["x_rev"], g["r_ref"], strict=True)}
    return {k: ((a - b) / b if b else None) for k, (a, b) in sums.items()}


# ================================================================================== breakdown
def _level_key(level: str) -> str:
    return "series_id" if level == "series" else level


def _breakdown_rows(sc: _Scope, df: pd.DataFrame, level: str, p_node: float) -> list[dict[str, Any]]:
    """Every member of ``level`` as a PlanRow (unsorted, Pareto fields filled)."""
    ctx, cmp, measure = sc.ctx, sc.cmp, sc.measure
    key = _level_key(level)
    groups = _group(df, key)
    realized = _realized(ctx, sc.ids, key) if cmp in FC_CMPS else {}
    min_abs = max(ROW_SHARE_OF_P * abs(p_node), MIN_ABS_VARIANCE[measure])
    rows = []
    for member, r in groups:
        facts = _facts(r, cmp, measure)
        tags = _tags(facts, cmp)
        row = {
            "key": str(member),
            "label": common.member_label(ctx, level, str(member)),
            "x": facts["x"],
            "p": facts["p"],
            "variance": facts["variance"],
            "variance_pct": facts["variance_pct"],
            "share_of_adverse": None,
            "share_of_favorable": None,
            "cum_share": None,
            "prob_hit": facts["prob_hit"],
            "growth_plan": facts["g_plan"],
            "growth_fc": facts["g_fc"],
            "realized_variance_pct": realized.get(member) if cmp in FC_CMPS else None,
            "effects": facts["effects"],
            "tags": tags,
            "is_exception": _passes(facts, _primary(tags), min_abs),
            "n_series": facts["n_series"],
            "drillable": level in common.DIMS and facts["n_series"] > 1,
        }
        if level == "series":
            row["series_id"] = str(member)
        rows.append(row)
    _pareto(rows)
    return rows


def _pareto(rows: list[dict[str, Any]]) -> None:
    """share_of_adverse / share_of_favorable and the cumulative share within each direction (§4.2.6)."""
    adverse = sorted((r for r in rows if r["variance"] < 0), key=lambda r: r["variance"])
    favorable = sorted((r for r in rows if r["variance"] > 0), key=lambda r: -r["variance"])
    for group, field_name in ((adverse, "share_of_adverse"), (favorable, "share_of_favorable")):
        gross = sum(r["variance"] for r in group)
        cum = 0.0
        for r in group:
            share = r["variance"] / gross if gross else 0.0
            cum += share
            r[field_name] = share
            r["cum_share"] = cum


def _ordered(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Adverse rows by V ascending, then favourable rows by V descending, then zero rows."""
    adverse = sorted((r for r in rows if r["variance"] < 0), key=lambda r: r["variance"])
    favorable = sorted((r for r in rows if r["variance"] > 0), key=lambda r: -r["variance"])
    zero = [r for r in rows if r["variance"] == 0]
    return adverse + favorable + zero


def _concentration(rows: list[dict[str, Any]], variance: float, n_members: int) -> dict[str, Any] | None:
    """Smallest k (1..3) whose cumulative share reaches 50% of the losses (V < 0) or of the gain (V ≥ 0)."""
    if variance < 0:
        group = sorted((r for r in rows if r["variance"] < 0), key=lambda r: r["variance"])
    else:
        group = sorted((r for r in rows if r["variance"] > 0), key=lambda r: -r["variance"])
    if not group:
        return None
    n_top = len(group)
    for i, r in enumerate(group, start=1):
        if (r["cum_share"] or 0.0) >= PARETO_SHARE - 1e-12:
            n_top = i
            break
    n_top = max(1, min(PARETO_MAX, n_top, len(group)))
    return {
        "n_top": n_top,
        "share": group[n_top - 1]["cum_share"],
        "members": [r["label"] for r in group[:n_top]],
        "n_members": n_members,
    }


# ================================================================================== KPIs and headline
def _main_driver(cmp: str, facts: dict[str, Any]) -> tuple[str, float] | None:
    """Largest effect in the direction of V (most negative when V < 0, most positive otherwise)."""
    cands = [(EFFECT_SHORT[k], v) for k, v in facts["effects"].items() if v is not None]
    if cmp == "ac_pl":
        cands = [c for c in cands if c[0] != EFFECT_SHORT["events"]]
    if cmp == "fc_tg" and facts["challenge"] is not None:
        cands.append((EFFECT_SHORT["challenge"], -facts["challenge"]))
    if not cands:
        return None
    return min(cands, key=lambda c: c[1]) if facts["variance"] < 0 else max(cands, key=lambda c: c[1])


def _classification_label(sc: _Scope, facts: dict[str, Any]) -> str | None:
    """Class label of the target for the node (same rules as the S&OP feasibility, ``assess``)."""
    cls = None
    if not sc.filters:
        # Company node: the full S&OP rules of ``assess`` (capacity and growth checks), so the label
        # matches the report's "Meta" chapter. Other nodes use the probability rule alone, which
        # keeps drill-downs fast (``assess`` costs ~0,3 s per new scope).
        months = [f"{d:%Y-%m-%d}" for d in sc.months]
        try:
            a = common.cached(
                sc.ctx,
                "plan.assess",
                months,
                sc.measure,
                build=lambda: assess(sc.ctx, {}, months, sc.measure),
            )
        except Exception:
            a = {}
        cls = a.get("classification") if a.get("available") else None
    if cls is None and facts["sigma_n"] is not None:
        cls, _ = classify(facts["p"], facts["x"], facts["sigma_n"], facts["p10"] or 0.0, facts["p90"] or 0.0)
    return CLASSES[cls]["label"] if cls in CLASSES else None


def _kpis(sc: _Scope, facts: dict[str, Any], conc: dict[str, Any] | None, level: str) -> list[dict[str, Any]]:
    cmp, m = sc.cmp, sc.measure
    v, vpct, x, p = facts["variance"], facts["variance_pct"], facts["x"], facts["p"]
    tone = "neutral" if vpct is not None and abs(vpct) < ALIGNED_VPCT else ("good" if v >= 0 else "bad")
    if cmp == "ac_pl":
        label1 = (
            "Desvio vs orçamento (U12M)" if sc.period.code == "u12m" else f"Desvio vs orçamento ({sc.period.label})"
        )
    else:
        label1 = "Desvio vs meta" if cmp == "fc_tg" else "Desvio vs orçamento"
    k1 = {
        "id": "variance",
        "label": label1,
        "value": v,
        "format": "currency_signed" if m == "revenue" else "units",
        "text": None,
        "delta": ptbr.pct(vpct, 1, signed=True) if vpct is not None else None,
        "delta_tone": tone,
        "hint": f"{_fmt(x, m)} vs {_fmt(p, m)}",
    }
    if cmp == "fc_pl":
        k2 = {
            "id": "prob_hit",
            "label": "Chance de atingir o orçamento",
            "value": facts["prob_hit"],
            "format": "percent",
            "text": None,
            "delta": None,
            "delta_tone": "neutral",
            "hint": f"faixa P10–P90 {_fmt(facts['p10'], m)}–{_fmt(facts['p90'], m)}",
        }
    elif cmp == "fc_tg":
        k2 = {
            "id": "prob_hit",
            "label": "Chance de bater a meta",
            "value": facts["prob_hit"],
            "format": "percent",
            "text": None,
            "delta": None,
            "delta_tone": "neutral",
            "hint": _classification_label(sc, facts),
        }
    else:
        k2 = {
            "id": "attainment",
            "label": "Atingimento do orçamento",
            "value": _ratio(x, p),
            "format": "percent",
            "text": None,
            "delta": None,
            "delta_tone": "neutral",
            "hint": f"{_fmt(x, m)} de {_fmt(p, m)}",
        }
    if conc:
        n = conc["n_members"]
        word = common.LEVEL_PLURAL[level] if n != 1 else common.LEVEL_SINGULAR[level]
        k3 = {
            "id": "concentration",
            "label": "Concentração",
            "value": conc["n_top"],
            "format": "text",
            "text": f"{conc['n_top']} de {n} {word}",
            "delta": None,
            "delta_tone": "neutral",
            "hint": f"{ptbr.pct(conc['share'])} {'das perdas' if v < 0 else 'do ganho'}",
        }
    else:
        k3 = {
            "id": "concentration",
            "label": "Concentração",
            "value": None,
            "format": "text",
            "text": "—",
            "delta": None,
            "delta_tone": "neutral",
            "hint": "sem desvios relevantes",
        }
    driver = _main_driver(cmp, facts)
    if driver:
        name, value = driver
        share = f" ({ptbr.pct(value / v)} do desvio)" if v else ""
        k4 = {
            "id": "main_driver",
            "label": "Principal fator",
            "value": value,
            "format": "text",
            "text": name,
            "delta": None,
            "delta_tone": "neutral",
            "hint": f"{_fmt(value, m, signed=True)}{share}",
        }
    else:
        k4 = {
            "id": "main_driver",
            "label": "Principal fator",
            "value": None,
            "format": "text",
            "text": "—",
            "delta": None,
            "delta_tone": "neutral",
            "hint": "sem desvios relevantes",
        }
    return [k1, k2, k3, k4]


def _headline_facts(sc: _Scope, facts: dict[str, Any], rows: list[dict[str, Any]], level: str) -> dict[str, Any]:
    adverse = sorted((r for r in rows if r["variance"] < 0), key=lambda r: r["variance"])
    favorable = sorted((r for r in rows if r["variance"] > 0), key=lambda r: -r["variance"])
    return {
        "cmp": sc.cmp,
        "measure": sc.measure,
        "node": common.node_label(sc.filters),
        "period_phrase": common.period_phrase(sc.period),
        "period_label": sc.period.label,
        "level": level,
        "level_label": common.LEVEL_LABEL.get(level),
        "x": facts["x"],
        "p": facts["p"],
        "variance": facts["variance"],
        "variance_pct": facts["variance_pct"],
        "top": adverse[0]["label"] if adverse else None,
        "top_share": adverse[0]["share_of_adverse"] if adverse else None,
        "top_fav": favorable[0]["label"] if favorable else None,
        "top_fav_share": favorable[0]["share_of_favorable"] if favorable else None,
    }


# ================================================================================== shapes
def _envelope(ctx: PlanningContext, cmp: str, measure: str, period: common.Period) -> dict[str, Any]:
    return {
        "available": True,
        "cmp": cmp,
        "lens": "plan",
        "measure": measure,
        "period": common.period_dict(period),
    }


def _node(ctx: PlanningContext, filters: dict[str, Any], n_series: int) -> dict[str, Any]:
    return {"label": common.node_label(filters), "path": common.node_path(filters), "n_series": n_series}


def _memo(ctx: PlanningContext, name: str, *args: Any, build: Any) -> dict[str, Any]:
    """Whole-response cache (§4.7); callers get a private copy."""
    return copy.deepcopy(common.cached(ctx, name, *args, build=build))


# ================================================================================== summary
def summary(
    ctx: PlanningContext,
    filters: dict[str, Any],
    cmp: str,
    period: str | None,
    measure: str,
    level: str | None,
    limit: int = 12,
) -> dict[str, Any]:
    per = common.parse_period(ctx, cmp, period)
    level = level or common.next_level(filters)
    return _memo(
        ctx,
        "plan.summary",
        filters,
        cmp,
        per.code,
        measure,
        level,
        limit,
        build=lambda: _summary(ctx, filters, cmp, per, measure, level, limit),
    )


def _summary(
    ctx: PlanningContext,
    filters: dict[str, Any],
    cmp: str,
    per: common.Period,
    measure: str,
    level: str,
    limit: int,
) -> dict[str, Any]:
    sc = _scope(ctx, filters, cmp, per, measure)
    out = _envelope(ctx, cmp, measure, per)
    out["periods"] = common.period_options(ctx, cmp)
    out["comparisons"] = common.comparisons(ctx)
    out["node"] = _node(ctx, filters, len(sc.ids))
    levels = common.level_options(cmp, filters, len(sc.ids))
    if not sc.available:
        out.update(
            available=False,
            reason=sc.reason,
            headline="",
            notices=sc.notices,
            kpis=[],
            breakdown={
                "level": level,
                "level_label": common.LEVEL_LABEL[level],
                "next_level": common.level_after(filters, level),
                "levels": levels,
                "rows": [],
                "others": None,
                "n_members": 0,
            },
            concentration=None,
        )
        return out
    df = _with_effects(sc.cells, _pbar(sc.cells), measure)
    node_facts = _facts(_node_row(df), cmp, measure)
    all_rows = _breakdown_rows(sc, df, level, node_facts["p"])
    n_members = len(all_rows)
    conc = _concentration(all_rows, node_facts["variance"], n_members)
    keep = sorted(all_rows, key=lambda r: -abs(r["variance"]))[:limit]
    keep_ids = {id(r) for r in keep}
    shown = [r for r in _ordered(all_rows) if id(r) in keep_ids]
    rest = [r for r in all_rows if id(r) not in keep_ids]
    others = {"n": len(rest), "value": float(sum(r["variance"] for r in rest))} if rest else None
    out.update(
        headline=narrative.summary_headline(_headline_facts(sc, node_facts, all_rows, level), cmp),
        notices=sc.notices,
        kpis=_kpis(sc, node_facts, conc, level),
        breakdown={
            "level": level,
            "level_label": common.LEVEL_LABEL[level],
            "next_level": common.level_after(filters, level),
            "levels": levels,
            "rows": shown,
            "others": others,
            "n_members": n_members,
        },
        concentration=conc,
    )
    return out


# ================================================================================== focus
def _member_filter(df: pd.DataFrame, level: str, member: str) -> pd.DataFrame:
    return df[df[_level_key(level)] == str(member)]


def _price_ref(df: pd.DataFrame) -> pd.Series:
    """p_ref,c = R_ref / Q_ref when Q_ref > 0, else the compared price (effects reference)."""
    return (df["er"] / df["eq"].where(df["eq"] > 0)).where(df["eq"] > 0, df["p_x"])


def paasche_gap(df: pd.DataFrame, regular_only: bool = True) -> float | None:
    """Mix-free realized price index vs the budget price (Paasche, §4.2.3 drivers).

    Σ Q_ac·(p_ac − p_ref) / Σ Q_ac·p_ref over the cells with Q_ref > 0 and Q_ac > 0 (and, when
    ``regular_only``, promotion = 0). ``df`` needs q_stat, p_x, eq, er and promotion.
    """
    mask = (df["eq"] > 0) & (df["q_stat"] > 0)
    if regular_only:
        mask &= df["promotion"].fillna(0) <= 0
    if not mask.any():
        return None
    d = df[mask]
    p_ref = _price_ref(d)
    den = float((d["q_stat"] * p_ref).sum())
    return float((d["q_stat"] * (d["p_x"] - p_ref)).sum()) / den if den else None


def _events_by_type(ctx: PlanningContext, cmp: str, df: pd.DataFrame) -> list[dict[str, Any]]:
    """Σ events_c by the event type of the overrides active in each cell (split by uplift share)."""
    oc = _override_cells(ctx, cmp)
    if oc.empty or df.empty:
        return []
    cells = df[[*KEY, "events"]]
    m = oc.merge(cells, on=KEY, how="inner")
    if m.empty:
        return []
    su = m.groupby(KEY, observed=True)["u"].transform("sum")
    m["value"] = np.where(su != 0, m["events"] * m["u"] / su.where(su != 0, 1.0), 0.0)
    g = m.groupby("event_type").agg(value=("value", "sum"), n=("oid", "nunique")).reset_index()
    g = g.reindex(g["value"].abs().sort_values(ascending=False).index)
    return [{"event_type": r.event_type, "value": float(r.value), "n": int(r.n)} for r in g.itertuples()]


def _drivers(ctx: PlanningContext, cmp: str, measure: str, df: pd.DataFrame, pbar: float) -> dict[str, Any]:
    out: dict[str, Any] = {
        "plan_price_premium": None,
        "price_promo": None,
        "reg_price_gap": None,
        "avg_price_gap": None,
        "volume_split": None,
        "events": [],
    }
    if cmp in FC_CMPS:
        den = float((df["eq"] * df["p_fc"]).sum())
        out["plan_price_premium"] = float(df["er"].sum()) / den - 1 if den > 0 else None
        out["events"] = _events_by_type(ctx, cmp, df)
        return out
    if measure == "revenue":
        promo = df["promotion"].fillna(0) > 0
        out["price_promo"] = float(df.loc[promo, "price"].sum())
    out["reg_price_gap"] = paasche_gap(df, regular_only=True)
    out["avg_price_gap"] = paasche_gap(df, regular_only=False)
    out["volume_split"] = volume_split(df, pbar if measure == "revenue" else 1.0)
    return out


def volume_split(df: pd.DataFrame, factor: float) -> dict[str, float] | None:
    """§4.2.4 split of the ac_pl volume effect: anticipated by the backtest forecast, demand surprise
    and cells not covered by the backtest. anticipated + surprise + uncovered = Σ vol_c.
    None when no cell is covered."""
    if df.empty:
        return None
    cov = df["f_bt"].notna()
    coverage = float(cov.mean())
    if coverage == 0:
        return None
    a, f, q = df["q_stat"], df["f_bt"], df["eq"]
    return {
        "anticipated": float(((f - q)[cov]).sum() * factor),
        "surprise": float(((a - f)[cov]).sum() * factor),
        "uncovered": float(((a - q)[~cov]).sum() * factor),
        "coverage": coverage,
    }


def _bridge(cmp: str, measure: str, facts: dict[str, Any]) -> list[dict[str, Any]]:
    rev = measure == "revenue"
    eff = facts["effects"]
    steps: list[dict[str, Any]] = []

    def step(key: str, label: str, value: float, kind: str, help_: str, notation: str | None = None) -> None:
        s: dict[str, Any] = {"key": key, "label": label, "value": float(value), "kind": kind, "help": help_}
        if notation:
            s["notation"] = notation
        steps.append(s)

    if cmp == "fc_tg":
        step("reference", "Meta", facts["p"], "total", HELP["reference_tg"], "TG")
        step("challenge", "Desafio comercial", -(facts["challenge"] or 0.0), "delta", HELP["challenge"])
        step("budget_subtotal", "Orçamento", facts["budget"], "subtotal", HELP["budget_subtotal"], "PL")
    else:
        step("reference", "Orçamento", facts["p"], "total", HELP["reference_pl"], "PL")
    step("volume", "Volume", eff["volume"], "delta", HELP["volume" if rev else "volume_units"])
    if rev:
        step("mix", "Mix", eff["mix"] or 0.0, "delta", HELP["mix"])
        step("price", "Preço", eff["price"] or 0.0, "delta", HELP["price_ac" if cmp == "ac_pl" else "price_fc"])
    if cmp in FC_CMPS:
        step(
            "events",
            "Eventos comerciais" if cmp == "fc_pl" else "Eventos",
            eff["events"] or 0.0,
            "delta",
            HELP["events"],
        )
        step("compared", "Consenso", facts["x"], "total", HELP["compared_fc"], "FC")
    else:
        step("compared", "Real", facts["x"], "total", HELP["compared_ac"], "AC")
    return steps


def _monthly(sc: _Scope, focus_level: str | None, focus: str | None) -> tuple[list[dict[str, Any]], list | None]:
    """Monthly rows over the comparison window ∩ plan months (the panel 'Quando aconteceu?' lets the
    user pick a month, so it always shows the whole window) and the quarter totals (fc_*)."""
    ctx, cmp, measure = sc.ctx, sc.cmp, sc.measure
    window = pd.DatetimeIndex(common.window(ctx, cmp)[0])
    pm = common.plan_months(ctx)
    months = window[window.isin(pm)]
    if not len(months):
        return [], ([] if cmp in FC_CMPS else None)
    df = _cells(ctx, cmp, measure, sc.ids, months)
    if focus_level and focus is not None:
        df = _member_filter(df, focus_level, focus)
    has_target = bool((df["tg"] > 0).any())
    g = df.groupby("date", sort=True)[["x", "ref", "ly", "tg", "xk", "sk", "sk2"]].sum()
    rows = []
    for d, r in g.to_dict("index").items():
        x, p = float(r["x"]), float(r["ref"])
        low = high = None
        if cmp in FC_CMPS:
            raw = math.sqrt(max(0.0, (1 - RHO) * r["sk2"] + RHO * r["sk"] ** 2))
            sigma = raw * (x / r["xk"]) if r["xk"] > 0 else 0.0
            low, high = max(0.0, x - Z90 * sigma), x + Z90 * sigma
        rows.append(
            {
                "date": f"{pd.Timestamp(d):%Y-%m-%d}",
                "x": x,
                "p": p,
                "py": float(r["ly"]),
                "target": float(r["tg"]) if has_target else None,
                "low": low,
                "high": high,
                "variance": x - p,
                "variance_pct": _ratio(x - p, p),
            }
        )
    if cmp not in FC_CMPS:
        return rows, None
    by_date = {r["date"]: r["variance"] for r in rows}
    quarters = []
    for code, qm in common.quarters(ctx):
        covered = [f"{d:%Y-%m-%d}" for d in qm if f"{d:%Y-%m-%d}" in by_date]
        if not covered:
            continue
        quarters.append(
            {
                "code": code,
                "label": common.quarter_label(int(code[1:]), pd.DatetimeIndex(qm)),
                "start": covered[0],
                "end": covered[-1],
                "variance": float(sum(by_date[d] for d in covered)),
            }
        )
    return rows, quarters


def _lag_label(ctx: PlanningContext) -> str:
    return common.cached(ctx, "plan.lag_label", build=lambda: common.lag_label(common.run_params(ctx)["fold_horizon"]))


def _single_path(filters: dict[str, Any]) -> dict[str, str]:
    out = {}
    for dim in common.DIMS:
        vals = common._values((filters or {}).get(dim))
        if len(vals) == 1:
            out[dim] = vals[0]
    return out


def _entity(
    sc: _Scope,
    level: str | None,
    member: str | None,
    label: str,
    facts: dict[str, Any],
    series_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Entity handed to ``rootcause.actions_for`` (prefill source)."""
    path = _single_path(sc.filters)
    ent: dict[str, Any] = {
        "cmp": sc.cmp,
        "measure": sc.measure,
        "level": level,
        "member": member,
        "label": label,
        "path": path,
        "filters": {k: list(v) if isinstance(v, list | tuple) else [v] for k, v in (sc.filters or {}).items()},
        "variance": facts["variance"],
        "variance_pct": facts["variance_pct"],
        "challenge": facts.get("challenge"),
        "months": [f"{d:%Y-%m-%d}" for d in sc.months],
        "horizon": [f"{d:%Y-%m-%d}" for d in sc.ctx.future_dates],
        "customer": member if level == "customer" else path.get("customer"),
        "sku": member if level == "sku" else path.get("sku"),
    }
    for dim in ("region", "channel", "category", "brand"):
        ent[dim] = member if level == dim else path.get(dim)
    if series_row is not None:
        ent.update(
            series_id=series_row["series_id"],
            customer=series_row["customer"],
            sku=series_row["sku"],
            region=series_row["region"],
            channel=series_row["channel"],
            category=series_row["category"],
        )
    elif level == "series" and member:
        cust, _, sku = str(member).partition(common.SERIES_SEP)
        ent.update(series_id=member, customer=cust, sku=sku)
    return ent


def _distribution_lever(sc: _Scope, ids: pd.Index, facts: dict[str, Any]) -> float | None:
    """Distribution change that alone closes the gap to the target (``feasibility._levers``, as in
    ``assess().levers``): the 'Simular cenário' prefill of the tag 'desafio_comercial' (§4.4)."""
    x, p = facts["x"], facts["p"]
    if sc.cmp != "fc_tg" or x <= 0 or p <= x or not len(ids):
        return None
    try:
        levers = feasibility_levers(sc.ctx, pd.Index(ids), (p - x) / x, x, sc.measure, len(sc.months))
    except Exception:  # elasticities unavailable: the button keeps its scope prefill only
        return None
    for lv in levers or []:
        change = _f(lv.get("required_change"))
        if lv.get("lever") == "Distribution" and change is not None:
            return round(change, 4)
    return None


def _with_lever(sc: _Scope, code: str, entity: dict[str, Any], ids: pd.Index, facts: dict[str, Any]) -> dict:
    if code == "desafio_comercial":
        lever = _distribution_lever(sc, ids, facts)
        if lever is not None:
            entity = {**entity, "distribution_change_pct": lever}
    return entity


def _actions(
    sc: _Scope,
    code: str,
    entity: dict[str, Any],
    ask_level: str | None,
    ask_member: str | None,
    facts: dict[str, Any],
    ids: pd.Index | None = None,
) -> list[dict[str, Any]]:
    """Actions of the primary tag (§4.4) plus 'Perguntar à IA' with a probed question (§4.3.3)."""
    entity = _with_lever(sc, code, entity, ids if ids is not None else sc.ids, facts)
    acts = [dict(a) for a in (rootcause.actions_for(code, entity, sc.ctx) or [])]
    question = narrative.ai_question(sc.cmp, ask_level, ask_member, {"variance": facts["variance"]})
    if question and not any(a.get("kind") == "ask_ai" for a in acts):
        acts.append({"kind": "ask_ai", "label": ASK_AI_LABEL, "prefill": {"question": question}})
    return acts


def _series_menu(
    sc: _Scope, code: str, entity: dict[str, Any], facts: dict[str, Any], drawer: bool = False
) -> list[dict[str, Any]]:
    """Full action menu of one series (exceptions row "Ações" / drawer action bar), built by
    ``rootcause.menu_actions`` exactly as in the forecast lens: open (ficha | workspace), create an
    adjustment, simulate and ask the AI, each item taking the primary tag's own prefill (§2.3.4, §2.3.6)."""
    entity = _with_lever(sc, code, entity, pd.Index([entity["series_id"]]), facts)
    return [dict(a) for a in (rootcause.menu_actions(code, entity, sc.ctx, drawer=drawer) or [])]


def focus(
    ctx: PlanningContext,
    filters: dict[str, Any],
    cmp: str,
    period: str | None,
    measure: str,
    focus_level: str | None = None,
    focus: str | None = None,
) -> dict[str, Any]:
    per = common.parse_period(ctx, cmp, period)
    if focus is not None and str(focus) == "":
        focus = None
    if focus is not None and not focus_level:
        focus_level = common.next_level(filters)
    if focus is None:
        focus_level = None
    return _memo(
        ctx,
        "plan.focus",
        filters,
        cmp,
        per.code,
        measure,
        focus_level,
        focus,
        build=lambda: _focus(ctx, filters, cmp, per, measure, focus_level, focus),
    )


def _empty_focus(out: dict[str, Any], reason: str, label: str) -> dict[str, Any]:
    out.update(
        available=False,
        reason=reason,
        focus={"level": None, "member": None, "label": label},
        headline="",
        bridge=None,
        bridge_note=None,
        drivers=None,
        causes=None,
        split=None,
        by_model=None,
        fva=None,
        monthly=[],
        quarters=None,
        diagnosis=[],
        actions=[],
        tags=[],
    )
    return out


def _focus(
    ctx: PlanningContext,
    filters: dict[str, Any],
    cmp: str,
    per: common.Period,
    measure: str,
    focus_level: str | None,
    focus: str | None,
) -> dict[str, Any]:
    sc = _scope(ctx, filters, cmp, per, measure)
    out = _envelope(ctx, cmp, measure, per)
    node_label = common.node_label(filters)
    if not sc.available:
        return _empty_focus(out, sc.reason or common.MSG_NO_SERIES, node_label)
    pbar = _pbar(sc.cells)  # a selected member keeps the parent node's P̄ (same effects as its ONDE row)
    df_node = _with_effects(sc.cells, pbar, measure)
    df = df_node
    label = node_label
    if focus_level and focus is not None:
        df = _member_filter(df_node, focus_level, focus)
        if df.empty:
            return _empty_focus(out, common.MSG_NO_SERIES, str(focus))
        label = common.member_label(ctx, focus_level, str(focus))
    facts = _facts(_node_row(df), cmp, measure)
    tags = _tags(facts, cmp)
    primary = _primary(tags)
    focus_ids = pd.Index(df["series_id"].astype(str).unique(), dtype=object)
    rv = _realized(ctx, focus_ids, None).get("__node__") if cmp in FC_CMPS else None
    recurrent = _recurrent(facts["variance"], rv)
    drivers = _drivers(ctx, cmp, measure, df, pbar)
    monthly, quarters = _monthly(sc, focus_level, focus)

    if focus_level and focus is not None:
        headline = narrative.focus_headline(
            {
                "cmp": cmp,
                "measure": measure,
                "node": node_label,
                "member": label,
                "level": focus_level,
                "period_phrase": common.period_phrase(per),
                "period_label": per.label,
                "x": facts["x"],
                "p": facts["p"],
                "variance": facts["variance"],
                "variance_pct": facts["variance_pct"],
                "tag_code": primary,
                "tag_label": tags[0]["label"] if tags else None,
                "realized_variance_pct": rv,
                "recurrent": recurrent,
            },
            cmp,
        )
    else:
        level = common.next_level(filters)
        rows = _breakdown_rows(sc, df_node, level, facts["p"])
        headline = narrative.summary_headline(_headline_facts(sc, facts, rows, level), cmp)

    events = drivers["events"] or []
    top_event = max(events, key=lambda e: abs(e["value"])) if events else None
    diag_facts = {
        "cmp": cmp,
        "measure": measure,
        "node": node_label,
        "member": label if focus is not None else None,
        "level": focus_level,
        "label": label,
        "x": facts["x"],
        "p": facts["p"],
        "variance": facts["variance"],
        "variance_pct": facts["variance_pct"],
        "g_plan": facts["g_plan"],
        "g_fc": facts["g_fc"],
        "challenge": facts["challenge"],
        "effects": facts["effects"],
        "vol": facts["effects"]["volume"],
        "mix": facts["effects"]["mix"],
        "price": facts["effects"]["price"],
        "events": facts["effects"]["events"],
        "realized_variance_pct": rv,
        "recurrent": recurrent,
        "plan_price_premium": drivers["plan_price_premium"],
        "reg_price_gap": drivers["reg_price_gap"],
        "avg_price_gap": drivers["avg_price_gap"],
        "price_promo": drivers["price_promo"],
        "volume_split": drivers["volume_split"],
        "lag_label": _lag_label(ctx),
        "events_list": events,
        "n_events": int(sum(e["n"] for e in events)),
        "top_event": top_event["event_type"] if top_event else None,
        "top_event_value": top_event["value"] if top_event else None,
        "tags": tags,
        "tag_code": primary,
        "tag_label": tags[0]["label"] if tags else None,
    }
    entity = _entity(sc, focus_level, focus, label, facts)
    ask_level, ask_member = focus_level, focus
    if focus_level == "series" and focus is not None:  # a series is asked about through its customer
        ask_level, ask_member = "customer", entity.get("customer")
    out.update(
        focus={"level": focus_level, "member": focus, "label": label},
        headline=headline,
        bridge=_bridge(cmp, measure, facts),
        bridge_note=BRIDGE_NOTE if measure == "revenue" else BRIDGE_NOTE_UNITS,
        drivers=drivers,
        causes=None,
        split=None,
        by_model=None,
        fva=None,
        monthly=monthly,
        quarters=quarters,
        diagnosis=list(narrative.plan_diagnosis(diag_facts, cmp) or [])[:3],
        actions=_actions(sc, primary, entity, ask_level, ask_member, facts, focus_ids),
        tags=tags,
        effects=facts["effects"],
        realized_variance_pct=rv,
    )
    return out


# ================================================================================== exceptions
def exceptions(
    ctx: PlanningContext,
    filters: dict[str, Any],
    cmp: str,
    period: str | None,
    measure: str,
    focus_level: str | None = None,
    focus: str | None = None,
    direction: str = "adverse",
    limit: int = 15,
    offset: int = 0,
) -> dict[str, Any]:
    per = common.parse_period(ctx, cmp, period)
    if direction not in ("adverse", "favorable", "all"):
        raise common.DeviationError(common.MSG_INVALID_DIRECTION)
    if focus is not None and str(focus) == "":
        focus = None
    if focus is not None and not focus_level:
        focus_level = common.next_level(filters)
    if focus is None:
        focus_level = None

    def ranked() -> tuple[_Scope, list[dict[str, Any]]]:
        return common.cached(
            ctx,
            "plan.exceptions.ranked",
            filters,
            cmp,
            per.code,
            measure,
            focus_level,
            focus,
            direction,
            build=lambda: _ranked_exceptions(ctx, filters, cmp, per, measure, focus_level, focus, direction),
        )

    def page() -> dict[str, Any]:
        sc, items = ranked()
        out: dict[str, Any] = {
            "total": len(items),
            "rows": [_exception_row(sc, it) for it in items[offset : offset + limit]],
        }
        if not sc.available:
            out.update(available=False, reason=sc.reason)
        return out

    return _memo(
        ctx,
        "plan.exceptions",
        filters,
        cmp,
        per.code,
        measure,
        focus_level,
        focus,
        direction,
        limit,
        offset,
        build=page,
    )


def _ranked_exceptions(
    ctx: PlanningContext,
    filters: dict[str, Any],
    cmp: str,
    per: common.Period,
    measure: str,
    focus_level: str | None,
    focus: str | None,
    direction: str,
) -> tuple[_Scope, list[dict[str, Any]]]:
    """All exception series of the scope, sorted (|V|·p_dir for fc_*, |V| for ac_pl)."""
    sc = _scope(ctx, filters, cmp, per, measure)
    if not sc.available:
        return sc, []
    df = _with_effects(sc.cells, _pbar(sc.cells), measure)
    if focus_level and focus is not None:
        df = _member_filter(df, focus_level, focus)
    if df.empty:
        return sc, []
    p_scope = float(df["ref"].sum())
    min_abs = max(SERIES_SHARE_OF_P * abs(p_scope), MIN_ABS_VARIANCE[measure])
    groups = _group(df, "series_id")
    items = []
    for sid, r in groups:
        facts = _facts(r, cmp, measure)
        v = facts["variance"]
        if (direction == "adverse" and v >= 0) or (direction == "favorable" and v <= 0):
            continue
        tags = _tags(facts, cmp)
        if not _passes(facts, _primary(tags), min_abs):
            continue
        weight = abs(v) * (facts["p_dir"] if facts["p_dir"] is not None else 1.0)
        items.append({"series_id": str(sid), "facts": facts, "tags": tags, "_sort": weight})
    items.sort(key=lambda it: (-it["_sort"], it["series_id"]))
    return sc, items


def _series_row(ctx: PlanningContext, series_id: str) -> dict[str, Any]:
    """Master row of a series as a dict (one cached lookup table instead of a set_index per row)."""
    table = common.cached(ctx, "plan.series_records", build=lambda: ctx.series.set_index("series_id").to_dict("index"))
    return table[series_id]


def _exception_row(sc: _Scope, it: dict[str, Any]) -> dict[str, Any]:
    ctx = sc.ctx
    s = _series_row(ctx, it["series_id"])
    facts, tags = it["facts"], it["tags"]
    primary = _primary(tags)
    srow = {
        "series_id": it["series_id"],
        "customer": str(s["customer"]),
        "sku": str(s["sku"]),
        "region": str(s["region"]),
        "channel": str(s["channel"]),
        "category": str(s["category"]),
    }
    label = f"{s['customer']} · {s['sku']} {s['product']}"
    entity = _entity(sc, "series", it["series_id"], label, facts, srow)
    return {
        **srow,
        "label": label,
        "product": str(s["product"]),
        "impact": abs(facts["x_rev"] - facts["r_ref"]),
        "x": facts["x"],
        "p": facts["p"],
        "variance": facts["variance"],
        "variance_pct": facts["variance_pct"],
        "prob_hit": facts["prob_hit"],
        "top_cause": None,
        "confidence": _str_or_none(s.get("confidence")),
        "champion": _str_or_none(s.get("champion")),
        "series_type_label": ptbr.series_type(_str_or_none(s.get("series_type"))),
        "tags": tags,
        "recommended_action": rootcause.recommended_action(primary),
        "actions": _series_menu(sc, primary, entity, facts),
    }


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return str(v)


# ================================================================================== series
def series(ctx: PlanningContext, series_id: str, cmp: str, period: str | None, measure: str) -> dict[str, Any]:
    per = common.parse_period(ctx, cmp, period)
    common.require_series(ctx, series_id)
    return _memo(
        ctx,
        "plan.series",
        series_id,
        cmp,
        per.code,
        measure,
        build=lambda: _series(ctx, series_id, cmp, per, measure),
    )


def _future_overrides(ctx: PlanningContext, s: dict[str, Any]) -> list[dict[str, Any]]:
    ov = ctx.overrides
    if ov is None or ov.empty:
        return []
    cust = ov["customer"].fillna("")
    sku = ov["sku"].fillna("")
    mask = ((cust == "") | (cust == s["customer"])) & ((sku == "") | (sku == s["sku"]))
    mask &= pd.to_datetime(ov["date"]).isin(ctx.future_dates)
    out = []
    for o in ov[mask].sort_values("date").to_dict("records"):
        out.append(
            {
                "date": f"{pd.Timestamp(o['date']):%Y-%m-%d}",
                "event_type": ptbr.label(ptbr.EVENT_TYPE, o.get("event_type")) or ptbr.NA,
                "uplift_pct": float(_f(o.get("uplift_pct")) or 0.0),
                "comment": _str_or_none(o.get("comment")),
            }
        )
    return out


def _series(ctx: PlanningContext, series_id: str, cmp: str, per: common.Period, measure: str) -> dict[str, Any]:
    s = _series_row(ctx, series_id)
    filters = {"customer": [str(s["customer"])], "sku": [str(s["sku"])]}
    sc = _scope(ctx, filters, cmp, per, measure)
    label = f"{s['customer']} · {s['sku']} {s['product']}"
    out: dict[str, Any] = {
        "available": sc.available,
        "cmp": cmp,
        "lens": "plan",
        "measure": measure,
        "period": common.period_dict(per),
        "series_id": series_id,
        "label": label,
        "header": {
            "customer": str(s["customer"]),
            "sku": str(s["sku"]),
            "product": str(s["product"]),
            "region": str(s["region"]),
            "channel": str(s["channel"]),
            "category": str(s["category"]),
            "series_type_label": ptbr.series_type(_str_or_none(s.get("series_type"))),
            "confidence": _str_or_none(s.get("confidence")),
            "champion": _str_or_none(s.get("champion")),
            "challenger": _str_or_none(s.get("challenger")),
        },
        "summary": {
            "reference": None,
            "compared": None,
            "variance": None,
            "variance_pct": None,
            "realized_variance_pct": None,
        },
        "timeline": records(timeline(ctx, filters, measure, history_months=24)),
        "evidence": None,
        "months": None,
        "effects": None,
        "tags": [],
        "recommended_action": rootcause.recommended_action("volume"),
        "actions": [],
        "future_overrides": _future_overrides(ctx, s),
        "notices": sc.notices,
    }
    if not sc.available:
        out["reason"] = sc.reason
        return out
    df = sc.cells[sc.cells["series_id"] == series_id]
    df = _with_effects(df, _pbar(df), measure)  # the series is its own node: own P̄
    facts = _facts(_node_row(df), cmp, measure)
    tags = _tags(facts, cmp)
    primary = _primary(tags)
    rv = _realized(ctx, pd.Index([series_id]), None).get("__node__") if cmp in FC_CMPS else None
    monthly, _ = _monthly(sc, None, None)
    srow = {
        "series_id": series_id,
        "customer": str(s["customer"]),
        "sku": str(s["sku"]),
        "region": str(s["region"]),
        "channel": str(s["channel"]),
        "category": str(s["category"]),
    }
    entity = _entity(sc, "series", series_id, label, facts, srow)
    out.update(
        summary={
            "reference": facts["p"],
            "compared": facts["x"],
            "variance": facts["variance"],
            "variance_pct": facts["variance_pct"],
            "realized_variance_pct": rv,
            "prob_hit": facts["prob_hit"],
        },
        months=monthly,
        effects=facts["effects"],
        tags=tags,
        recommended_action=rootcause.recommended_action(primary),
        actions=_series_menu(sc, primary, entity, facts, drawer=True),
    )
    return out
