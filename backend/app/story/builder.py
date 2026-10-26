"""Builds the 7-chapter executive story (``GET /api/story``, spec §4.5).

Contract: ``Story`` in ``frontend/src/types/story.ts`` ({available, reason?, reference, governing_thought,
scqa, chapters[7]}). The measure is fixed to revenue; ``filters`` uses region | channel | category in the
UI (all six dimensions accepted). Results are cached per filters with ``deviations.common.cached``.

Single source of numbers: each chapter reads the same ``deviations.service`` / ``trust`` / ``assess`` call
the deep dive (or the S&OP endpoints) use, keeps the raw numbers in ``chapter.facts`` and writes its
sentences from them (``story.templates``), so the report, the deep dive and the export never disagree.
"""

from __future__ import annotations

import copy
from typing import Any

import pandas as pd

from app.deviations import common, service
from app.fva.fva import fva_report
from app.services import datasets, ptbr
from app.services import trust as trust_service
from app.services.context import PlanningContext, filter_ids, horizon_totals, timeline
from app.sop.feasibility import CLASSES, assess, feasibility_by

from . import decisions as D
from . import templates as T

NO_RUN = "Ainda não há uma execução de forecast concluída."
ALL_ROWS = 100_000  # summary limit that returns every breakdown member
VARIANCE_BARS = 8  # rows of the Gap chapter's visual (+ "Demais")
GAP_LEVELS = ("customer", "category", "sku")  # first not fixed by the scope with ≥ 2 members
SCOPE_DIMS = ("region", "channel", "customer", "category", "brand", "sku")


# ================================================================================== scope helpers
def _values(v: Any) -> list[str]:
    if v is None or v == "" or v == []:
        return []
    return [str(x) for x in (v if isinstance(v, list | tuple | set) else [v])]


def _normalise(filters: dict[str, Any] | None) -> dict[str, list[str]]:
    return {d: _values((filters or {}).get(d)) for d in SCOPE_DIMS if _values((filters or {}).get(d))}


def _scope_path(filters: dict[str, list[str]]) -> dict[str, str]:
    """Deep-dive path of the report scope (one member per dimension)."""
    return {d: v[0] for d, v in filters.items() if len(v) == 1}


def _gap_level(ctx: PlanningContext, filters: dict[str, list[str]], ids: pd.Index) -> str:
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    for lv in GAP_LEVELS:
        if not filters.get(lv) and s[lv].nunique() >= 2:
            return lv
    return "series"


def _free_level(filters: dict[str, list[str]], prefs: tuple[str, ...] = ("region", "channel", "customer")) -> str:
    """Preferred breakdown level unless the scope already fixes it."""
    for lv in prefs:
        if not filters.get(lv):
            return lv
    return common.next_level(filters)


def _float(v: Any) -> float | None:
    return T.num(v)


def _span(months: pd.DatetimeIndex) -> str:
    """'out/2025–set/2026' (a single month label for a one-month window)."""
    if not len(months):
        return ptbr.NA
    a, b = months.min(), months.max()
    return ptbr.month_label(a) if a == b else f"{ptbr.month_label(a)}–{ptbr.month_label(b)}"


# ================================================================================== sources
class _Sources:
    """Every engine call of the story, made once (most are also cached by the engines themselves)."""

    def __init__(self, ctx: PlanningContext, filters: dict[str, list[str]], ids: pd.Index) -> None:
        self.ctx, self.filters, self.ids = ctx, filters, ids
        self.has_plan = not ctx.plan.empty
        self.h = len(ctx.future_dates)
        self.level = _gap_level(ctx, filters, ids)
        self.meta_level = _free_level(filters)
        self.totals = horizon_totals(ctx, ids, "revenue")
        self.quality = trust_service.scope_quality(ctx, ids)
        self.assess = assess(ctx, filters, None, "revenue")
        self.fc_pl = self._plan("fc_pl", self.level, ALL_ROWS)
        self.fc_pl_focus = self._focus("fc_pl")
        self.fc_tg = self._plan("fc_tg", self.meta_level)
        self.ac_pl = self._plan("ac_pl", self.level, ALL_ROWS)
        self.ac_pl_focus = self._focus("ac_pl")
        self.ac_pl_units = self._focus("ac_pl", "units")
        self.ac_fc = self._call(service.summary, ctx, filters, "ac_fc", None, "revenue", self.level)
        self.ac_fc_focus = self._call(service.focus, ctx, filters, "ac_fc", None, "revenue")
        self.fva = fva_report(ctx, filters)

    @staticmethod
    def _call(fn: Any, *args: Any) -> dict[str, Any]:
        try:
            out = fn(*args)
        except common.DeviationError as exc:  # never expected with the defaults; the chapter goes empty
            return {"available": False, "reason": exc.message}
        return out if isinstance(out, dict) else {"available": False}

    def _plan(self, cmp: str, level: str, limit: int = 12) -> dict[str, Any]:
        return self._call(service.summary, self.ctx, self.filters, cmp, None, "revenue", level, limit)

    def _focus(self, cmp: str, measure: str = "revenue") -> dict[str, Any]:
        return self._call(service.focus, self.ctx, self.filters, cmp, None, measure)


def _ok(d: dict[str, Any] | None) -> bool:
    return bool(d) and bool(d.get("available"))


def _kpi_value(summary: dict[str, Any], kpi_id: str) -> float | None:
    return next((_float(k.get("value")) for k in summary.get("kpis") or [] if k.get("id") == kpi_id), None)


def _bridge_value(focus: dict[str, Any], key: str) -> float | None:
    return next((_float(s.get("value")) for s in focus.get("bridge") or [] if s.get("key") == key), None)


def _no_emoji(display: dict[str, Any] | None) -> dict[str, Any]:
    return {k: v for k, v in (display or {}).items() if k != "emoji"}


# ================================================================================== chapter shell
def _chapter(
    cid: str,
    h: int,
    *,
    headline: str,
    context: str,
    visual_kind: str,
    visual_data: Any,
    facts: dict[str, Any],
    takeaways: list[dict[str, Any]] | None = None,
    investigate: dict[str, Any] | None = None,
    ask_ai: str | None = None,
    secondary_action: dict[str, str] | None = None,
    notice: str | None = None,
) -> dict[str, Any]:
    short, question = T.CHAPTERS[cid]
    empty = notice is not None
    title = T.TITLES[cid].format(h=h)
    return {
        "id": cid,
        "index": T.CHAPTER_IDS.index(cid) + 1,
        "title": title,
        "short": short.format(h=h),
        "question": question,
        "headline": title if empty else headline,
        "context": context,
        "takeaways": [] if empty else (takeaways or [])[:3],
        "status": "empty" if empty else "ok",
        "notice": notice,
        "visual": {"kind": visual_kind, "data": None if empty else visual_data},
        "investigate": None if empty or investigate is None else {"label": T.INVESTIGATE_LABEL, "params": investigate},
        "secondary_action": None if empty else secondary_action,
        "ask_ai": None if empty else ask_ai,
        "facts": {k: int(v) if isinstance(v, bool) else v for k, v in facts.items()},
    }


def _plan_notice(summary: dict[str, Any], ltm: bool = False) -> str:
    reason = summary.get("reason") if summary else None
    if reason == common.MSG_NO_SERIES:
        return T.NOTICE_NO_SERIES
    if reason == common.MSG_NO_PLAN_PERIOD:
        return T.NOTICE_NO_PLAN_LTM if ltm else T.NOTICE_NO_PLAN
    return T.NOTICE_NO_PLAN


# ================================================================================== chapters
def _realizado(src: _Sources, ref: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    s, f = src.ac_pl, src.ac_pl_focus
    ctx_line = f"Real × Orçamento · {ref['ltm_label']} · Receita (R$) · {ref['scope_label']}"
    if not (_ok(s) and _ok(f)):
        ch = _chapter(
            "realizado",
            src.h,
            headline="",
            context=ctx_line,
            visual_kind="bridge",
            visual_data=None,
            facts={},
            notice=_plan_notice(s, ltm=True),
        )
        return ch, {}
    ac, pl = _bridge_value(f, "compared") or 0.0, _bridge_value(f, "reference") or 0.0
    eff = f.get("effects") or {}
    drv = f.get("drivers") or {}
    monthly = f.get("monthly") or []
    py = sum(_float(r.get("py")) or 0.0 for r in monthly)
    targets = [_float(r.get("target")) for r in monthly]
    tg = sum(t for t in targets if t is not None) if any(t is not None for t in targets) else None
    u = src.ac_pl_units
    units_x, units_p = (_bridge_value(u, "compared"), _bridge_value(u, "reference")) if _ok(u) else (None, None)
    rows = (s.get("breakdown") or {}).get("rows") or []
    adverse = sorted((r for r in rows if r["variance"] < 0), key=lambda r: r["variance"])
    fav = sorted((r for r in rows if r["variance"] > 0), key=lambda r: -r["variance"])
    v = ac - pl
    facts = {
        "ac": ac,
        "pl": pl,
        "py": py or None,
        "tg": tg,
        "v": v,
        "v_pct": v / pl if pl else None,
        "units_pct": (units_x / units_p - 1) if units_x is not None and units_p else None,
        "vol": _float(eff.get("volume")),
        "mix": _float(eff.get("mix")),
        "price": _float(eff.get("price")),
        "price_promo": _float(drv.get("price_promo")),
        "reg_price_gap": _float(drv.get("reg_price_gap")),
        "avg_price_gap": _float(drv.get("avg_price_gap")),
        "ac_vs_py": (ac / py - 1) if py else None,
        "attain_pl": ac / pl if pl else None,
        "attain_tg": ac / tg if tg else None,
        "top_adv": adverse[0]["label"] if adverse else None,
        "top_adv_key": adverse[0]["key"] if adverse else None,
        "top_adv_v": adverse[0]["variance"] if adverse else None,
        "top_adv_share": adverse[0]["share_of_adverse"] if adverse else None,
        "top_fav": fav[0]["label"] if fav else None,
        "top_fav_key": fav[0]["key"] if fav else None,
        "top_fav_v": fav[0]["variance"] if fav else None,
    }
    ch = _chapter(
        "realizado",
        src.h,
        headline=T.realizado_headline(facts),
        context=ctx_line,
        visual_kind="bridge",
        visual_data={"steps": f.get("bridge") or [], "note": T.BRIDGE_NOTE},
        facts=facts,
        takeaways=T.realizado_takeaways(facts, src.level),
        investigate={"cmp": "ac_pl", "periodo": "u12m", "nivel": src.level},
        ask_ai=T.ASK_REALIZADO,
    )
    return ch, facts


def _precisao(src: _Sources, ref: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    s, f, q = src.ac_fc, src.ac_fc_focus, src.quality
    ctx_line = (
        f"Real × Estatístico (campeão) · backtest {ref['backtest_label']}, {ref['lag_label']} de antecedência · "
        f"WMAPE em unidades · {ref['scope_label']}"
    )
    if not (_ok(s) and _ok(f) and q):
        ch = _chapter(
            "precisao",
            src.h,
            headline="",
            context=ctx_line,
            visual_kind="cause_bars",
            visual_data=None,
            facts={},
            notice=T.NOTICE_NO_BACKTEST,
        )
        return ch, {}
    causes = f.get("causes") or []
    groups = {g: sum(float(c["share"]) for c in causes if c["group"] == g) for g in ("controllable", "inherent")}
    ctrl = [c for c in causes if c["group"] == "controllable"]
    cause1 = max(ctrl, key=lambda c: c["abs_error"]) if ctrl else None
    split = f.get("split") or {}
    fva = src.fva or {}
    stair = fva.get("stairstep") or {}
    has_history = common.has_overrides_history(src.ctx)
    events = [
        g
        for g in fva.get("by_event_type") or []
        if _float(g.get("fva_pp")) is not None and int(g.get("overrides") or 0) >= D.D6_MIN_OVERRIDES
    ]
    worst = min(events, key=lambda g: g["fva_pp"]) if events else None
    conc = s.get("concentration") or {}
    facts = {
        "wmape": q["wmape"],
        "naive": q["naive_wmape"],
        "gain_pp": q["gain_vs_naive_pp"],
        "bias": q["bias"],
        "bias_label": q["bias_label"],
        "controllable_share": groups["controllable"],
        "inherent_share": groups["inherent"],
        "cause1": cause1["label"] if cause1 else None,
        "cause1_code": cause1["code"] if cause1 else None,
        "cause1_share": cause1["share"] if cause1 else None,
        "systematic_share": _float(split.get("systematic_share")),
        "has_history": has_history,
        "fva_pp": _float(stair.get("fva_consensus_vs_statistical")) if has_history else None,
        "value_added": _float((fva.get("summary") or {}).get("value_added_pct")) if has_history else None,
        "worst_event": str(worst["event_type"]) if worst and has_history else None,
        "worst_event_pp": _float(worst["fva_pp"]) if worst and has_history else None,
        "n_top_err": conc.get("n_top"),
        "share_top_err": _float(conc.get("share")),
        "names": T.join_names(list(conc.get("members") or [])) or None,
        "total_abs_error": sum(float(c["abs_error"]) for c in causes),
    }
    if has_history:
        ask = T.ASK_PRECISAO_FVA
    else:
        ask = T.ASK_PRECISAO_OVER if (q["bias"] or 0.0) > 0 else T.ASK_PRECISAO_UNDER
    ch = _chapter(
        "precisao",
        src.h,
        headline=T.precisao_headline(facts),
        context=ctx_line,
        visual_kind="cause_bars",
        visual_data={
            "causes": causes,
            "total_abs_error": facts["total_abs_error"],
            "note": T.CAUSES_NOTE.format(lag=ref["lag_label"]),
        },
        facts=facts,
        takeaways=T.precisao_takeaways(facts, src.level),
        investigate={"cmp": "ac_fc", "periodo": "bt", "nivel": src.level},
        ask_ai=ask,
    )
    return ch, facts


def _band(src: _Sources) -> tuple[float | None, float | None]:
    """Consensus band P10–P90 (= ``assess().p10/p90``; spec §2.0 rule 6)."""
    a = src.assess
    if a.get("available"):
        return _float(a.get("p10")), _float(a.get("p90"))
    t = src.totals
    return _float(t.get("consensus_p10")), _float(t.get("consensus_p90"))


def _no_plan_monthly(src: _Sources) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Monthly consensus vs prior year (projecao without a plan): rows + peak month."""
    ctx = src.ctx
    tl = timeline(ctx, src.filters, "revenue", history_months=24)
    tl["date"] = pd.to_datetime(tl["date"])
    by_date = tl.set_index("date")
    rows = []
    for d in ctx.future_dates:
        x = _float(by_date.at[d, "consensus"]) if d in by_date.index else None
        base = _float(by_date.at[d, "base"]) if d in by_date.index else None
        p10 = _float(by_date.at[d, "p10"]) if d in by_date.index else None
        p90 = _float(by_date.at[d, "p90"]) if d in by_date.index else None
        ly_d = d - pd.DateOffset(years=1)
        py = _float(by_date.at[ly_d, "actual"]) if ly_d in by_date.index else None
        k = (x / base) if x is not None and base else 1.0
        rows.append(
            {
                "date": f"{d:%Y-%m-%d}",
                "x": x,
                "p": py,
                "py": py,
                "target": None,
                "low": p10 * k if p10 is not None else None,
                "high": p90 * k if p90 is not None else None,
                "variance": (x - py) if x is not None and py is not None else None,
                "variance_pct": (x / py - 1) if x is not None and py else None,
            }
        )
    valid = [r for r in rows if r["x"] is not None]
    peak = max(valid, key=lambda r: r["x"]) if valid else None
    return rows, {"peak_month": peak["date"] if peak else None, "peak_value": peak["x"] if peak else None}


def _projecao(src: _Sources, ref: dict[str, Any], base: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    f = src.fc_pl_focus
    has_plan = src.has_plan and _ok(f) and _ok(src.fc_pl)
    p10, p90 = _band(src)
    facts: dict[str, Any] = {
        "has_plan": has_plan,
        "fc": base["fc"],
        "fc_vs_ltm": base["fc_vs_ltm"],
        "horizon_end": f"{src.ctx.future_dates.max():%Y-%m-%d}",
        "gap_pl": base["gap_pl"] if has_plan else None,
        "gap_tg": base["gap_tg"] if has_plan else None,
        "budget": base["budget"] if has_plan else None,
        "target": base["target"] if has_plan else None,
        "p10": p10,
        "p90": p90,
    }
    scope = ref["scope_label"]
    if has_plan:
        monthly, quarters = f.get("monthly") or [], f.get("quarters") or []
        wq = min(quarters, key=lambda q: q["variance"]) if quarters else None
        valid = [r for r in monthly if _float(r.get("variance")) is not None]
        wm = min(valid, key=lambda r: r["variance"]) if valid else None
        events = (f.get("drivers") or {}).get("events") or []
        facts.update(
            worst_q=wq["label"] if wq else None,
            worst_q_gap=wq["variance"] if wq else None,
            worst_q_start=wq.get("start") if wq else None,
            worst_q_end=wq.get("end") if wq else None,
            worst_month=wm["date"] if wm else None,
            worst_month_gap=wm["variance"] if wm else None,
            events=_float((f.get("effects") or {}).get("events")) or 0.0,
            n_events=int(sum(int(e.get("n") or 0) for e in events)),
        )
        visual = {"x_kind": "FC", "rows": monthly, "quarters": quarters, "x_label": "Consenso", "p_label": "Orçamento"}
        ctx_line = f"Consenso × Orçamento · {ref['horizon_label']} · Receita (R$) · {scope}"
        ask = None
        if wm:
            word = "abaixo" if wm["variance"] < 0 else "acima"
            ask = f"Por que o forecast de {T.MES_LONG(wm['date'])} está {word} do orçamento?"
    else:
        rows, peak = _no_plan_monthly(src)
        facts.update(peak, events=base["events_np"], n_events=base["n_events_np"])
        visual = {"x_kind": "FC", "rows": rows, "quarters": None, "x_label": "Consenso", "p_label": "Ano anterior"}
        ctx_line = f"Consenso × Ano anterior · {ref['horizon_label']} · Receita (R$) · {scope}"
        ask = None
    ch = _chapter(
        "projecao",
        src.h,
        headline=T.projecao_headline(facts),
        context=ctx_line,
        visual_kind="monthly_variance",
        visual_data=visual,
        facts=facts,
        takeaways=T.projecao_takeaways(facts),
        investigate={"cmp": "fc_pl", "periodo": "h", "nivel": src.meta_level} if has_plan else None,
        ask_ai=ask,
    )
    return ch, facts


def _gap(src: _Sources, ref: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    s, f, level = src.fc_pl, src.fc_pl_focus, src.level
    word = common.LEVEL_SINGULAR[level]
    ctx_line = f"Consenso × Orçamento por {word} · {ref['horizon_label']} · Receita (R$) · {ref['scope_label']}"
    if not (_ok(s) and _ok(f)):
        ch = _chapter(
            "gap",
            src.h,
            headline="",
            context=ctx_line,
            visual_kind="variance_bars",
            visual_data=None,
            facts={},
            notice=_plan_notice(s),
        )
        return ch, {}, []
    rows = (s.get("breakdown") or {}).get("rows") or []
    conc = s.get("concentration") or {}
    adverse = sorted((r for r in rows if r["variance"] < 0), key=lambda r: r["variance"])
    fav = sorted((r for r in rows if r["variance"] > 0), key=lambda r: -r["variance"])
    v = _kpi_value(s, "variance") or 0.0
    p_node = _bridge_value(f, "reference") or 0.0
    eff = f.get("effects") or {}
    facts: dict[str, Any] = {
        "v": v,
        "v_pct": v / p_node if p_node else None,
        "level": level,
        "n_top": conc.get("n_top") if v < 0 else None,
        "share": _float(conc.get("share")) if v < 0 else None,
        "vol": _float(eff.get("volume")),
        "mix": _float(eff.get("mix")),
        "price": _float(eff.get("price")),
        "events": _float(eff.get("events")),
        "plan_price_premium": _float((f.get("drivers") or {}).get("plan_price_premium")),
        "n_pos": len(fav),
        "pos": sum(r["variance"] for r in fav) if fav else None,
        "top_pos": fav[0]["label"] if fav else None,
        "top_pos_v": fav[0]["variance"] if fav else None,
        "p_top1": _float(adverse[0]["prob_hit"]) if adverse else None,
        "rv_top1": _float(adverse[0]["realized_variance_pct"]) if adverse else None,
    }
    for i, r in enumerate(adverse[:3], start=1):
        tags = r.get("tags") or []
        facts[f"n{i}"] = r["label"]
        facts[f"key{i}"] = r["key"]
        facts[f"v{i}"] = r["variance"]
        facts[f"tag{i}"] = tags[0]["label"] if tags else None
        facts[f"tag{i}_code"] = tags[0]["code"] if tags else None
        if i <= 2:
            facts[f"gp{i}"] = _float(r.get("growth_plan"))
            facts[f"gf{i}"] = _float(r.get("growth_fc"))
    keep = sorted(rows, key=lambda r: -abs(r["variance"]))[:VARIANCE_BARS]
    keep_ids = {id(r) for r in keep}
    shown = [r for r in adverse + fav + [r for r in rows if r["variance"] == 0] if id(r) in keep_ids]
    rest = [r for r in rows if id(r) not in keep_ids]
    others = {"n": len(rest), "value": float(sum(r["variance"] for r in rest))} if rest else None
    top1 = adverse[0]["key"] if v < 0 and adverse else (fav[0]["key"] if fav else None)
    investigate = {"cmp": "fc_pl", "periodo": "h", "nivel": level}
    if top1:
        investigate["sel"] = top1
    ask = None
    if top1 and level in T.ARTICLE_LEVEL:
        ask = f"Como está {T.ARTICLE_LEVEL[level]} {top1}?"
    ch = _chapter(
        "gap",
        src.h,
        headline=T.gap_headline(facts),
        context=ctx_line,
        visual_kind="variance_bars",
        visual_data={"rows": shown, "others": others, "level": level, "level_label": common.LEVEL_LABEL[level]},
        facts=facts,
        takeaways=T.gap_takeaways(facts, level),
        investigate=investigate,
        ask_ai=ask,
    )
    return ch, facts, rows


def _meta(src: _Sources, ref: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    a = src.assess
    ctx_line = f"Consenso × Meta · {ref['horizon_label']} · Receita (R$) · {ref['scope_label']}"
    if not (src.has_plan and a.get("available")):
        notice = T.NOTICE_NO_PLAN if not src.has_plan else T.NOTICE_NO_TARGET
        ch = _chapter(
            "meta",
            src.h,
            headline="",
            context=ctx_line,
            visual_kind="feasibility_range",
            visual_data=None,
            facts={},
            notice=notice,
        )
        return ch, {}
    n_months = len(a.get("months") or []) or src.h
    lever = T.pick_lever(a.get("levers") or [], n_months)
    lever_code = lever["lever"] if lever else None
    lever_change = _float(lever["required_change"]) if lever else None
    feas_dim = _free_level(src.filters, ("region", "channel", "customer"))
    by = feasibility_by(src.ctx, feas_dim, src.filters, "revenue")
    r1 = by[0] if by else None
    facts = {
        "target": _float(a.get("target")),
        "prob": _float(a.get("probability")),
        "classification": a.get("classification"),
        "class_label": CLASSES.get(a.get("classification"), {}).get("label"),
        "gap": (_float(a.get("target")) or 0.0) - (_float(a.get("consensus")) or 0.0),
        "lever": lever_code,
        "lever_change": lever_change,
        "required_growth": _float(a.get("required_growth")),
        "forecast_growth": _float(a.get("forecast_growth")),
        "historical_growth": _float(a.get("historical_growth")),
        "p10": _float(a.get("p10")),
        "p90": _float(a.get("p90")),
        "feas_dim": feas_dim,
        "r1": str(r1["member"]) if r1 else None,
        "p1": _float(r1["probability"]) if r1 else None,
        "n_by": len(by),
        "n_aggr": sum(1 for r in by if r.get("classification") == "AGGRESSIVE"),
    }
    secondary = None
    if lever_code:
        levers = {}
        if lever_code == "Distribution":
            levers["distribution_change_pct"] = lever_change
        elif lever_code == "Marketing":
            levers["marketing_change_pct"] = lever_change
        secondary = {"label": T.SIMULATE_LABEL, "route": T.scenarios_route(_scope_path(src.filters), levers)}
    ch = _chapter(
        "meta",
        src.h,
        headline=T.meta_headline(facts),
        context=ctx_line,
        visual_kind="feasibility_range",
        visual_data={
            "p10": _float(a.get("p10")),
            "p50": _float(a.get("p50")),
            "p90": _float(a.get("p90")),
            "target": _float(a.get("target")),
            "budget": _float(a.get("budget")),
            "consensus": _float(a.get("consensus")),
            "probability": _float(a.get("probability")),
            "classification": a.get("classification"),
            "display": _no_emoji(a.get("display")),
        },
        facts=facts,
        takeaways=T.meta_takeaways(facts, list(a.get("reasons") or [])),
        investigate={"cmp": "fc_tg", "periodo": "h", "nivel": src.meta_level},
        ask_ai=T.ASK_META,
        secondary_action=secondary,
    )
    return ch, facts


def _events_no_plan(src: _Sources) -> tuple[float, int]:
    """Σ incremental revenue over H and the number of commercial overrides touching the scope."""
    f = src.ctx.forecast
    f = f[f["series_id"].isin(src.ids) & f["date"].isin(src.ctx.future_dates)]
    events = float((f["incremental"] * f["price"]).sum()) if not f.empty else 0.0
    ov = src.ctx.overrides
    if ov is None or ov.empty:
        return events, 0
    s = src.ctx.series[src.ctx.series["series_id"].isin(src.ids)]
    cust, sku = ov["customer"].fillna(""), ov["sku"].fillna("")
    hit = (cust.eq("") | cust.isin(s["customer"])) & (sku.eq("") | sku.isin(s["sku"]))
    hit &= pd.to_datetime(ov["date"]).isin(src.ctx.future_dates)
    return events, int(hit.sum())


# ================================================================================== story
def _reference(ctx: PlanningContext, filters: dict[str, list[str]], has_plan: bool) -> dict[str, Any]:
    params = common.run_params(ctx)
    bt = common.backtest_months(ctx)
    ds = datasets.get_dataset(ctx.version) or {}
    return {
        "cycle_label": ptbr.month_label(ctx.future_dates.min()),
        "last_actual": f"{ctx.last_actual:%Y-%m-%d}",
        "horizon_label": _span(pd.DatetimeIndex(ctx.future_dates)),
        "horizon_months": len(ctx.future_dates),
        "ltm_label": _span(pd.DatetimeIndex(ctx.ltm_dates)),
        "backtest_label": _span(bt) if len(bt) else ptbr.NA,
        "lag_label": common.lag_label(params["fold_horizon"]),
        "scope_label": common.node_label(filters),
        "dataset_version": ctx.version,
        "run_id": ctx.run_id,
        "plan_source": ds.get("plan_source"),
        "plan_derived": common.plan_derived(ctx),
        "has_plan": has_plan,
    }


def build_story(ctx: PlanningContext, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    if not ctx.has_run:
        return {"available": False, "reason": NO_RUN}
    norm = _normalise(filters)
    return copy.deepcopy(common.cached(ctx, "story.build", norm, build=lambda: _build(ctx, norm)))


def _build(ctx: PlanningContext, filters: dict[str, list[str]]) -> dict[str, Any]:
    ids = filter_ids(ctx, filters)
    if not len(ids):
        return {"available": False, "reason": T.NOTICE_NO_SERIES}
    src = _Sources(ctx, filters, ids)
    h = src.h
    ref = _reference(ctx, filters, src.has_plan)
    t = src.totals
    fc, ac_ltm, prior = (
        _float(t.get("consensus")) or 0.0,
        _float(t.get("actual_ltm")),
        _float(t.get("actual_prior_ltm")),
    )
    gap_pl = _kpi_value(src.fc_pl, "variance") if _ok(src.fc_pl) else None
    gap_tg = _kpi_value(src.fc_tg, "variance") if _ok(src.fc_tg) else None
    budget = _bridge_value(src.fc_pl_focus, "reference") if _ok(src.fc_pl_focus) else None
    events_np, n_events_np = _events_no_plan(src)
    base = {
        "fc": fc,
        "fc_vs_ltm": (fc / ac_ltm - 1) if ac_ltm else None,
        "gap_pl": gap_pl,
        "gap_tg": gap_tg,
        "budget": budget,
        "target": _float(src.assess.get("target")) if src.assess.get("available") else None,
        "events_np": events_np,
        "n_events_np": n_events_np,
    }

    realizado, rf = _realizado(src, ref)
    precisao, pf = _precisao(src, ref)
    projecao, _ = _projecao(src, ref, base)
    gap, gf, gap_rows = _gap(src, ref)
    meta, mf = _meta(src, ref)

    # ---- decisions (chapter 7) and the summary (chapter 1) reuse the facts above
    lever_txt = T.lever_text(mf.get("lever"), mf.get("lever_change")) if mf else None
    dec_facts = {
        "level": src.level,
        "meta_level": src.meta_level,
        "scope_path": _scope_path(filters),
        "gap_rows": gap_rows,
        "p_node": budget,
        "price_effect": gf.get("price"),
        "plan_price_premium": gf.get("plan_price_premium"),
        "reg_price_gap": rf.get("reg_price_gap"),
        "causes": ((precisao.get("visual") or {}).get("data") or {}).get("causes") if pf else [],
        "assess": src.assess if src.has_plan else {},
        "lever_text": lever_txt,
        "simulate_route": (meta.get("secondary_action") or {}).get("route"),
        "fva": src.fva,
        "ids": ids,
        "series_revenue": trust_service.series_revenue(ctx),
        "annualise": h / max(len(common.backtest_months(ctx)), 1),
    }
    decisions = D.build_decisions(ctx, filters, dec_facts)
    decisoes = _chapter(
        "decisoes",
        h,
        headline=T.decisoes_headline(decisions),
        context=(f"Desvios, viabilidade, erro e ajustes · {ref['horizon_label']} · {ref['scope_label']}"),
        visual_kind="decision_table",
        visual_data={"rows": decisions},
        facts={
            "n": len(decisions),
            **{f"d{i}_code": d["code"] for i, d in enumerate(decisions[:3], start=1)},
            **{f"d{i}_short": d["short"] for i, d in enumerate(decisions[:3], start=1)},
            **{f"d{i}_impact": d["impact"] for i, d in enumerate(decisions[:3], start=1)},
        },
        investigate={"cmp": "fc_pl", "periodo": "h", "nivel": "series"} if src.has_plan else None,
    )

    q = src.quality or {}
    has_plan = bool(src.has_plan and gap_pl is not None)
    a = src.assess if src.assess.get("available") else {}
    p10, p90 = _band(src)
    verdict = q.get("verdict_code")
    rfacts = {
        "has_plan": has_plan,
        "ac_ltm": ac_ltm,
        "ac_vs_py": (ac_ltm / prior - 1) if ac_ltm is not None and prior else None,
        "pl_ltm": rf.get("pl"),
        "attain_pl": rf.get("attain_pl"),
        "fc": fc,
        "fc_vs_ltm": base["fc_vs_ltm"],
        "gap_pl": gap_pl,
        "gap_pl_pct": (gap_pl / budget) if gap_pl is not None and budget else None,
        "gap_tg": gap_tg,
        "target": _float(a.get("target")),
        "prob_tg": _float(a.get("probability")),
        "class_code": a.get("classification"),
        "class_tg": CLASSES.get(a.get("classification"), {}).get("label"),
        "n_top": gf.get("n_top"),
        "share_top": gf.get("share"),
        "level": src.level,
        "accuracy": q.get("accuracy"),
        "bias": q.get("bias"),
        "verdict": verdict,
        "verdict_label": trust_service.VERDICT_SHORT.get(verdict) if verdict else None,
        "p10": p10,
        "p90": p90,
    }
    governing = T.governing_thought(rfacts, h)
    resumo = _chapter(
        "resumo",
        h,
        headline=governing,
        context=(
            f"Realizado {ref['ltm_label']} · projeção {ref['horizon_label']} · Receita (R$) · {ref['scope_label']}"
        ),
        visual_kind="kpis",
        visual_data={"cards": T.resumo_cards(rfacts, h)},
        facts=rfacts,
        investigate=(
            {"cmp": "fc_pl", "periodo": "h", "nivel": src.level}
            if has_plan
            else ({"cmp": "ac_fc", "periodo": "bt", "nivel": src.level} if pf else None)
        ),
        ask_ai=T.ASK_RESUMO,
    )
    return {
        "available": True,
        "reference": ref,
        "governing_thought": governing,
        "scqa": T.scqa(rfacts, h, ref["horizon_label"], decisions),
        "chapters": [resumo, realizado, precisao, projecao, gap, meta, decisoes],
    }
