"""Shared vocabulary of the deviation deep dive: comparisons, periods, levels, errors and the cache.

Comparisons (``cmp``):

* plan lens: ``fc_pl`` (Consenso × Orçamento), ``fc_tg`` (Consenso × Meta), ``ac_pl`` (Real × Orçamento, U12M)
* forecast lens: ``ac_fc`` (Real × Estatístico campeão), ``ac_cs`` (Real × Consenso histórico)

Every user-facing string here is pt-BR (spec §2.3.3, §4.2.1, §4.3.3).
"""

from __future__ import annotations

import json
import math
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

import pandas as pd

from app import db
from app.forecasting.panel import SERIES_SEP
from app.services import ptbr
from app.services.context import FILTER_DIMS, PlanningContext

T = TypeVar("T")

# ------------------------------------------------------------------------------------------ comparisons
CMP_PLAN = ("fc_pl", "fc_tg", "ac_pl")
CMP_FORECAST = ("ac_fc", "ac_cs")
CMPS = CMP_PLAN + CMP_FORECAST
DEFAULT_PERIOD = {"fc_pl": "h", "fc_tg": "h", "ac_pl": "u12m", "ac_fc": "bt", "ac_cs": "bt"}
MEASURES = ("revenue", "units")

CMP_LABEL = {
    "fc_pl": "Consenso × Orçamento",
    "fc_tg": "Consenso × Meta",
    "ac_pl": "Real × Orçamento",
    "ac_fc": "Real × Estatístico (campeão)",
    "ac_cs": "Real × Consenso histórico (com ajustes)",
}

# ------------------------------------------------------------------------------------------ levels
DRILL_ORDER = ["region", "channel", "customer", "category", "sku"]
DIMS = list(FILTER_DIMS)  # region, channel, customer, category, brand, sku
PLAN_LEVELS = [*DIMS, "series"]
FORECAST_LEVELS = [*PLAN_LEVELS, "champion", "series_type"]
LEVEL_LABEL = {
    **{d: ptbr.DIMENSION[d] for d in DIMS},
    "series": "Série",
    "champion": "Modelo campeão",
    "series_type": "Padrão de demanda",
}
# Lower-case plural used inside sentences: "2 de 14 clientes".
LEVEL_PLURAL = {
    "region": "regiões",
    "channel": "canais",
    "customer": "clientes",
    "category": "categorias",
    "brand": "marcas",
    "sku": "SKUs",
    "series": "séries",
    "champion": "modelos",
    "series_type": "padrões de demanda",
}
LEVEL_SINGULAR = {
    "region": "região",
    "channel": "canal",
    "customer": "cliente",
    "category": "categoria",
    "brand": "marca",
    "sku": "SKU",
    "series": "série",
    "champion": "modelo",
    "series_type": "padrão de demanda",
}
SERIES_LEVEL_MAX = 60  # 'Série' is offered as a breakdown only up to this many series (or a fixed customer/SKU)

# ------------------------------------------------------------------------------------------ messages
MSG_INVALID_CMP = "Comparação inválida. Use fc_pl, fc_tg, ac_pl, ac_fc ou ac_cs."
MSG_INVALID_PERIOD = "Período inválido para esta comparação."
MSG_INVALID_LEVEL = "Nível inválido para esta comparação."
MSG_INVALID_MEASURE = "Medida inválida. Use revenue ou units."
MSG_NO_PLAN = "Não há orçamento/meta nesta base."
MSG_NO_PLAN_PERIOD = "Não há orçamento/meta para este período."
MSG_NO_OVERRIDES = "Sem histórico de ajustes comerciais nesta base."
MSG_NO_RUN = "Ainda não há uma execução de forecast concluída."
MSG_NO_SERIES = "Nenhuma série neste recorte."
MSG_INVALID_DIRECTION = "Direção inválida. Use adverse, favorable ou all."
NOTICE_DERIVED_PLAN = "Orçamento estimado automaticamente — desvios ilustrativos"
NOTICE_PARTIAL_PLAN = "Orçamento disponível para {n} de {m} meses do período; a comparação usa apenas esses meses."

_MONTH_CODE = re.compile(r"^(\d{4})-(\d{2})(?:-01)?$")


class DeviationError(ValueError):
    """Invalid request for the deviation endpoints: ``status`` (400/404) + a pt-BR message."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class Period:
    code: str
    label: str
    months: pd.DatetimeIndex
    kind: str  # "future" | "history" | "backtest"


# ------------------------------------------------------------------------------------------ validation
def lens_of(cmp: str) -> str:
    """'plan' | 'forecast' (raises DeviationError for an unknown comparison)."""
    validate_cmp(cmp)
    return "plan" if cmp in CMP_PLAN else "forecast"


def validate_cmp(cmp: str | None) -> str:
    if cmp not in CMPS:
        raise DeviationError(MSG_INVALID_CMP)
    return cmp


def validate_measure(cmp: str, measure: str | None) -> str:
    """Forecast lens is always measured in revenue impact (WMAPE itself is in units)."""
    if measure is None:
        measure = "revenue"
    if measure not in MEASURES:
        raise DeviationError(MSG_INVALID_MEASURE)
    return "revenue" if cmp in CMP_FORECAST else measure


def levels_for(cmp: str) -> list[str]:
    return FORECAST_LEVELS if lens_of(cmp) == "forecast" else PLAN_LEVELS


def validate_level(cmp: str, level: str | None) -> str | None:
    """None passes through (the caller then uses ``next_level``)."""
    if level is None or level == "":
        return None
    if level not in levels_for(cmp):
        raise DeviationError(MSG_INVALID_LEVEL)
    return level


# ------------------------------------------------------------------------------------------ periods
def _span(months: pd.DatetimeIndex) -> str:
    """'out/2025–set/2026' (or a single month label)."""
    if len(months) == 0:
        return ptbr.NA
    a, b = months.min(), months.max()
    return ptbr.month_label(a) if a == b else f"{ptbr.month_label(a)}–{ptbr.month_label(b)}"


def quarter_label(k: int, months: pd.DatetimeIndex) -> str:
    """'T1 · out–dez/2026'; across years 'T2 · dez/2026–fev/2027'; a 1-month quarter 'T5 · out/2027'."""
    a, b = months.min(), months.max()
    if a == b:
        return f"T{k} · {ptbr.month_label(a)}"
    if a.year == b.year:
        return f"T{k} · {ptbr.MONTHS_SHORT[a.month - 1]}–{ptbr.month_label(b)}"
    return f"T{k} · {ptbr.month_label(a)}–{ptbr.month_label(b)}"


def backtest_months(ctx: PlanningContext) -> pd.DatetimeIndex:
    if ctx.backtest is None or ctx.backtest.empty:
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(sorted(pd.to_datetime(ctx.backtest["date"]).unique()))


def window(ctx: PlanningContext, cmp: str) -> tuple[pd.DatetimeIndex, str]:
    """Full month window of a comparison and its kind: H (future), U12M (history) or BT (backtest)."""
    validate_cmp(cmp)
    if cmp in ("fc_pl", "fc_tg"):
        return pd.DatetimeIndex(ctx.future_dates), "future"
    if cmp == "ac_pl":
        return pd.DatetimeIndex(ctx.ltm_dates), "history"
    return backtest_months(ctx), "backtest"


def quarters(ctx: PlanningContext) -> list[tuple[str, pd.DatetimeIndex]]:
    """[(code 't1', months), ...] over the horizon H: T_k = H[3(k−1):3k]."""
    h = pd.DatetimeIndex(ctx.future_dates)
    return [(f"t{k + 1}", h[3 * k : 3 * k + 3]) for k in range(math.ceil(len(h) / 3))]


def _window_period(ctx: PlanningContext, cmp: str) -> Period:
    months, kind = window(ctx, cmp)
    code = DEFAULT_PERIOD[cmp]
    if kind == "future":
        label = f"Próximos {len(months)} meses ({_span(months)})"
    elif kind == "history":
        label = f"Últimos 12 meses ({_span(months)})"
    else:
        label = f"Janela de backtest ({_span(months)})"
    return Period(code, label, months, kind)


def parse_period(ctx: PlanningContext, cmp: str, code: str | None) -> Period:
    """Period code -> Period (spec §4.2.1). None/'' = the comparison default; invalid -> DeviationError 400.

    Allowed codes: fc_* ``h``, ``t1..t{ceil(h/3)}`` or ``YYYY-MM`` ∈ H; ac_pl ``u12m`` or ``YYYY-MM`` ∈ U12M;
    ac_fc/ac_cs ``bt`` or ``YYYY-MM`` ∈ BT. ``YYYY-MM-01`` is accepted and normalised to ``YYYY-MM``.
    """
    validate_cmp(cmp)
    code = (code or DEFAULT_PERIOD[cmp]).strip().lower()
    if code == DEFAULT_PERIOD[cmp]:
        return _window_period(ctx, cmp)
    months, kind = window(ctx, cmp)
    if kind == "future":
        for qcode, qmonths in quarters(ctx):
            if code == qcode:
                return Period(qcode, quarter_label(int(qcode[1:]), qmonths), qmonths, kind)
    m = _MONTH_CODE.match(code)
    if m:
        ts = pd.Timestamp(int(m.group(1)), int(m.group(2)), 1) if 1 <= int(m.group(2)) <= 12 else None
        if ts is not None and ts in months:
            return Period(f"{ts:%Y-%m}", ptbr.month_label(ts), pd.DatetimeIndex([ts]), kind)
    raise DeviationError(MSG_INVALID_PERIOD)


def period_options(ctx: PlanningContext, cmp: str) -> list[dict[str, str]]:
    """[{code, label}] for the 'Período' select: window, then quarters (fc_*), then each month."""
    base = _window_period(ctx, cmp)
    out = [{"code": base.code, "label": base.label}]
    if base.kind == "future":
        out += [{"code": q, "label": quarter_label(int(q[1:]), m)} for q, m in quarters(ctx)]
    out += [{"code": f"{d:%Y-%m}", "label": ptbr.month_label(d)} for d in base.months]
    return out


def period_phrase(period: Period) -> str:
    """Period as used inside a sentence: 'nos próximos 12 meses', 'nos últimos 12 meses',
    'na janela de backtest (out/2025–set/2026)', 'em T1 (out–dez/2026)', 'em out/2026'."""
    n = len(period.months)
    if period.code == "h":
        return f"nos próximos {n} {'mês' if n == 1 else 'meses'}"
    if period.code == "u12m":
        return "nos últimos 12 meses"
    if period.code == "bt":
        return f"na janela de backtest ({_span(period.months)})"
    if period.code.startswith("t"):
        head, _, span = period.label.partition(" · ")
        return f"em {head} ({span})" if span else f"em {head}"
    return f"em {period.label}"


# ------------------------------------------------------------------------------------------ nodes
def _values(v: Any) -> list[str]:
    if v is None or v == "" or v == []:
        return []
    return [str(x) for x in (v if isinstance(v, list | tuple | set) else [v])]


def next_level(filters: dict[str, Any] | None) -> str:
    """First DRILL_ORDER dimension not fixed by the filters, else 'series'."""
    f = filters or {}
    for dim in DRILL_ORDER:
        if not _values(f.get(dim)):
            return dim
    return "series"


def node_path(filters: dict[str, Any] | None) -> list[dict[str, str]]:
    """[{dim, member, label}] in filter-dimension order; several values of one dimension are joined."""
    f = filters or {}
    out = []
    for dim in DIMS:
        vals = _values(f.get(dim))
        if vals:
            member = ", ".join(vals)
            out.append({"dim": dim, "member": member, "label": f"{LEVEL_LABEL[dim]}: {member}"})
    return out


def node_label(filters: dict[str, Any] | None) -> str:
    """'Empresa toda' | 'Nordeste › Varejo Moderno'."""
    path = node_path(filters)
    return " › ".join(p["member"] for p in path) if path else "Empresa toda"


def require_series(ctx: PlanningContext, series_id: str) -> pd.Series:
    """Series master row or DeviationError 404 "Série 'Cliente · SKU' não encontrada"."""
    s = ctx.series
    hit = s[s["series_id"] == series_id]
    if hit.empty:
        raise DeviationError(f"Série '{str(series_id).replace(SERIES_SEP, ' · ')}' não encontrada", 404)
    return hit.iloc[0]


def level_options(cmp: str, filters: dict[str, Any] | None, n_series: int) -> list[dict[str, Any]]:
    """``breakdown.levels`` of the summary: {value, label, disabled, reason?} for the lens' levels.

    A dimension already fixed by the path is disabled ("Já filtrado: Sul"); ``series`` is enabled only
    when a customer or SKU is fixed or the node has at most ``SERIES_LEVEL_MAX`` series.
    """
    f = filters or {}
    out: list[dict[str, Any]] = []
    for lv in levels_for(cmp):
        opt: dict[str, Any] = {"value": lv, "label": LEVEL_LABEL[lv], "disabled": False}
        vals = _values(f.get(lv)) if lv in DIMS else []
        if vals:
            opt.update(disabled=True, reason=f"Já filtrado: {', '.join(vals)}")
        elif (
            lv == "series" and not (_values(f.get("customer")) or _values(f.get("sku"))) and n_series > SERIES_LEVEL_MAX
        ):
            opt.update(
                disabled=True, reason=f"Filtre um cliente ou SKU (ou um recorte com até {SERIES_LEVEL_MAX} séries)"
            )
        out.append(opt)
    return out


def level_after(filters: dict[str, Any] | None, level: str) -> str | None:
    """Level shown after drilling into a member of ``level`` (None for non-drillable levels)."""
    if level not in DIMS:
        return None
    return next_level({**(filters or {}), level: "__member__"})


def period_dict(period: Period) -> dict[str, Any]:
    """JSON shape of ``period``: {code, label, months ['YYYY-MM-DD'], kind}."""
    return {
        "code": period.code,
        "label": period.label,
        "months": [f"{d:%Y-%m-%d}" for d in period.months],
        "kind": period.kind,
    }


# ------------------------------------------------------------------------------------------ capabilities
def plan_months(ctx: PlanningContext) -> pd.DatetimeIndex:
    """PM: the months that have at least one plan row (budget/target) in the active base."""
    if ctx.plan is None or ctx.plan.empty:
        return pd.DatetimeIndex([])
    return cached(
        ctx, "common.plan_months", build=lambda: pd.DatetimeIndex(sorted(pd.to_datetime(ctx.plan["date"]).unique()))
    )


def plan_derived(ctx: PlanningContext) -> bool:
    """True when the base's plan was estimated automatically (``datasets.DERIVED_PLAN_SOURCE``)."""
    from app.services import datasets

    def build() -> bool:
        src = db.scalar("SELECT plan_source FROM datasets WHERE dataset_version = ?", [ctx.version])
        src = datasets.LEGACY_PLAN_SOURCES.get(src, src) if isinstance(src, str) else src
        return src == datasets.DERIVED_PLAN_SOURCE

    return cached(ctx, "common.plan_derived", build=build)


def has_overrides_history(ctx: PlanningContext) -> bool:
    """True when the base has historical commercial adjustments (needed by ``ac_cs``)."""
    return cached(
        ctx,
        "common.has_overrides_history",
        build=lambda: bool(
            db.scalar("SELECT COUNT(*) FROM historical_overrides WHERE dataset_version = ?", [ctx.version])
        ),
    )


def comparisons(ctx: PlanningContext) -> list[dict[str, Any]]:
    """The 'Comparação' select: {cmp, label, available, reason?} for the five comparisons (spec §2.3.3).

    ``reason`` is the label suffix shown on a disabled option ("sem orçamento nesta base").
    """
    h = len(ctx.future_dates)
    pm = plan_months(ctx)
    bt = backtest_months(ctx)
    labels = {
        "fc_pl": f"Consenso × Orçamento · próximos {h} meses",
        "fc_tg": f"Consenso × Meta · próximos {h} meses",
        "ac_pl": "Real × Orçamento · últimos 12 meses",
        "ac_fc": CMP_LABEL["ac_fc"],
        "ac_cs": CMP_LABEL["ac_cs"],
    }
    out = []
    for cmp in CMPS:
        reason = None
        if not ctx.has_run:
            reason = "sem execução de forecast"
        elif cmp in CMP_PLAN:
            win, _ = window(ctx, cmp)
            if len(pm) == 0:
                reason = "sem orçamento nesta base"
            elif not pd.DatetimeIndex(win).isin(pm).any():
                reason = "sem orçamento neste período"
        elif len(bt) == 0:
            reason = "sem backtest nesta execução"
        elif cmp == "ac_cs" and not has_overrides_history(ctx):
            reason = "sem histórico de ajustes"
        item: dict[str, Any] = {"cmp": cmp, "label": labels[cmp], "available": reason is None}
        if reason:
            item["reason"] = reason
        out.append(item)
    return out


def member_label(ctx: PlanningContext, level: str, key: str) -> str:
    """Display label of a breakdown member: 'Cliente · SKU produto' for series, else the member itself."""
    if level != "series":
        return str(key)
    labels = cached(
        ctx,
        "common.series_labels",
        build=lambda: {
            r["series_id"]: f"{r['customer']} · {r['sku']} {r['product']}"
            for r in ctx.series[["series_id", "customer", "sku", "product"]].to_dict("records")
        },
    )
    return labels.get(key) or str(key).replace(SERIES_SEP, " · ")


# ------------------------------------------------------------------------------------------ run params
def run_params(ctx: PlanningContext) -> dict[str, int]:
    """n_folds / fold_horizon / horizon of the active run (``forecast_runs.params_json``; RunParams defaults)."""
    from app.forecasting.worker import RunParams

    d = RunParams()
    out = {"n_folds": d.n_folds, "fold_horizon": d.fold_horizon, "horizon": d.horizon}
    if ctx.run_id:
        raw = db.scalar("SELECT params_json FROM forecast_runs WHERE run_id = ?", [ctx.run_id])
        try:
            params = json.loads(raw or "{}")
        except (TypeError, ValueError):
            params = {}
        for k in out:
            if isinstance(params.get(k), int | float):
                out[k] = int(params[k])
    return out


def lag_label(fold_horizon: int) -> str:
    """'1–3 meses' (fold_horizon = 3) or '1 mês' (fold_horizon = 1). Never hard-coded in texts."""
    return "1 mês" if int(fold_horizon) <= 1 else f"1–{int(fold_horizon)} meses"


# ------------------------------------------------------------------------------------------ cache
_cache: dict[tuple, Any] = {}
_cache_prefix: tuple | None = None
# Strong reference to the context that owns the cache. Saving an override drops the old context
# (``context.bump_overrides``) and CPython often allocates the rebuilt one at the same address, so
# ``id(ctx)`` alone could match and serve numbers from before the override. Holding the owner keeps
# its id from being reused while the cache is keyed on it.
_cache_owner: PlanningContext | None = None
_cache_lock = threading.Lock()


def _freeze(v: Any) -> Any:
    if isinstance(v, dict):
        return tuple(sorted((str(k), _freeze(x)) for k, x in v.items()))
    if isinstance(v, list | tuple | set | frozenset | pd.Index):
        items = [_freeze(x) for x in v]
        return tuple(sorted(items, key=repr)) if isinstance(v, set | frozenset) else tuple(items)
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    return v


def cached(ctx: PlanningContext, name: str, *args: Any, build: Callable[[], T]) -> T:
    """Memoise ``build()`` per (ctx.version, ctx.run_id, id(ctx), name, args).

    Same lifecycle as ``alerts.engine._cache``: the whole dict is cleared when the context changes
    (new dataset, new run or an override edit, which rebuilds the context). The owning context is
    compared by identity and kept alive, so a rebuilt context can never inherit its entries.
    """
    global _cache_prefix, _cache_owner
    prefix = (ctx.version, ctx.run_id, id(ctx))
    key = (*prefix, name, _freeze(args))
    with _cache_lock:
        if _cache_prefix != prefix or _cache_owner is not ctx:
            _cache.clear()
            _cache_prefix = prefix
            _cache_owner = ctx
        if key in _cache:
            return _cache[key]
    value = build()
    with _cache_lock:
        if _cache_prefix == prefix and _cache_owner is ctx:
            _cache[key] = value
    return value


def clear_cache() -> None:
    global _cache_prefix, _cache_owner
    with _cache_lock:
        _cache.clear()
        _cache_prefix = None
        _cache_owner = None
