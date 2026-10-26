"""Intent handlers: compute every number deterministically and draft the answer.

Each handler returns the structured AI response (answer, insights, metrics,
chart, table, recommendations, filters) plus ``facts`` - the only numbers
the LLM is allowed to use when it rewrites the explanation. Texts are written in
Portuguese (pt-BR, default) or English, following the question's language.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.alerts.engine import build_alerts
from app.fva.fva import fva_report
from app.scenarios.elasticity import estimate_elasticities, for_category
from app.scenarios.engine import ScenarioParams, simulate
from app.semantic_layer.catalog import SemanticQuery, run_query
from app.services.context import PlanningContext, backtest_metrics, clean, filter_ids, horizon_totals, timeline
from app.services.forecast_views import leaderboard
from app.sop.feasibility import assess

from .intents import Intent
from .nlg import (
    agree,
    article_pl,
    class_label,
    dec,
    dim_label,
    dim_title,
    event_type,
    group_value,
    lever,
    model_name,
    money,
    month_name,
    month_only,
    month_short,
    none_of,
    num,
    ordinal,
    pct,
    period_prep,
    period_text,
    planner,
    plural,
    pp,
    series_type,
    severity,
    t,
    units,
)

RANK_DIMS = ("sku", "customer", "region", "channel", "category", "brand")
# Most specific first: the dimension an entity is ranked against.
SPECIFICITY = ("sku", "customer", "brand", "category", "channel", "region")
SCOPE_ORDER = ("region", "channel", "category", "brand", "customer", "sku")
FEMININE = {"region", "category", "brand"}


# ------------------------------------------------------------------------------------- helpers
def _lang(it: Intent) -> str:
    return "en" if it.language == "en" else "pt"


def _label(ctx: PlanningContext, dim: str, member: Any) -> str:
    if dim == "sku":
        p = ctx.series.loc[ctx.series["sku"] == member, "product"]
        return f"{member} {p.iloc[0]}" if len(p) else str(member)
    return str(member)


def _value_text(ctx: PlanningContext, dim: str, v: Any) -> str:
    if isinstance(v, list | tuple | set):
        return ", ".join(_label(ctx, dim, x) for x in v)
    return _label(ctx, dim, v)


def _scope(ctx: PlanningContext, it: Intent, form: str = "plain") -> str:
    """Selection label. form: plain ('cliente Atlas'), art ('o cliente Atlas'), de ('do cliente Atlas')."""
    L = _lang(it)
    parts = [(d, it.filters[d]) for d in SCOPE_ORDER if it.filters.get(d) not in (None, "", [])]
    if not parts:
        if L == "en":
            return "the total portfolio"
        return {"plain": "portfólio total", "art": "o portfólio total", "de": "do portfólio total"}[form]
    texts = []
    for i, (d, v) in enumerate(parts):
        label = _value_text(ctx, d, v)
        if d == "sku":
            texts.append(label)
        else:
            texts.append(f"{dim_label(d, L)} {label}")
        if i == 0 and L != "en" and form != "plain":
            fem = d in FEMININE
            prefix = {"art": "a" if fem else "o", "de": "da" if fem else "do"}[form]
            texts[0] = f"{prefix} {texts[0]}"
    return ", ".join(texts)


def _cap(s: str) -> str:
    """Capitalize the first letter only ('SKUs' stays 'SKUs', not 'Skus')."""
    return s[:1].upper() + s[1:]


def _x_months(dates: Any, L: str) -> list[str]:
    return [month_short(d, L) for d in dates]


def _result(**kw: Any) -> dict[str, Any]:
    base = {
        "answer": "",
        "insights": [],
        "metrics": [],
        "chart": None,
        "table": None,
        "recommendations": [],
        "filters": {},
        "facts": {},
        "query": "",
    }
    base.update(kw)
    return clean(base)


def _safe_ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or not b:
        return None
    return a / b - 1


def _no_series(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = _lang(it)
    return _result(
        answer=t(
            L,
            f"No series found for {_scope(ctx, it)} in the active run.",
            f"Não encontrei séries para {_scope(ctx, it, 'art')} na execução ativa.",
        ),
        filters=it.filters,
    )


def _bt_metrics(ctx: PlanningContext, ids: pd.Index, months: list[str] | None = None) -> dict[str, Any]:
    """Backtest metrics (units) for a set of series: WMAPE, bias, accuracy, MAE, RMSE, sMAPE, MASE."""
    bt = ctx.backtest[ctx.backtest["series_id"].isin(ids)]
    if months:
        bt = bt[bt["date"].isin(pd.DatetimeIndex([pd.Timestamp(m) for m in months]))]
    out: dict[str, Any] = {
        "wmape": None,
        "bias": None,
        "accuracy": None,
        "mae": None,
        "rmse": None,
        "smape": None,
        "mase": None,
        "series": len(ids),
        "volume": 0.0,
    }
    total = float(bt["actual"].abs().sum()) if len(bt) else 0.0
    if total:
        e = bt["forecast"] - bt["actual"]
        w = float(e.abs().sum() / total)
        denom = (bt["forecast"].abs() + bt["actual"].abs()).replace(0, np.nan)
        out.update(
            wmape=w,
            bias=float(e.sum() / bt["actual"].sum()),
            accuracy=max(0.0, 1 - w),
            mae=float(e.abs().mean()),
            rmse=float(np.sqrt((e**2).mean())),
            smape=float((2 * e.abs() / denom).mean()),
            volume=float(bt["actual"].sum()),
        )
    if "mase" in ctx.series:
        m = ctx.series.loc[ctx.series["series_id"].isin(ids), "mase"].dropna()
        out["mase"] = float(m.median()) if len(m) else None
    return out


def _alerts_for(ctx: PlanningContext, filters: dict[str, Any] | None) -> list[dict[str, Any]]:
    alerts = build_alerts(ctx)
    if not filters:
        return alerts
    ids = set(filter_ids(ctx, filters))
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    customers, skus = set(s["customer"]), set(s["sku"])
    narrow = any(filters.get(k) for k in ("sku", "brand", "category"))
    out = []
    for a in alerts:
        e = a.get("entity") or {}
        if e.get("series_id"):
            keep = e["series_id"] in ids
        elif e.get("customer"):
            keep = e["customer"] in customers and not narrow
        elif e.get("sku"):
            keep = e["sku"] in skus
        else:
            keep = False
        if keep:
            out.append(a)
    return out


def _alert_entity(a: dict[str, Any]) -> str:
    e = a.get("entity") or {}
    return " ".join(str(x) for x in (e.get("customer"), e.get("sku")) if x) or str(e.get("region") or "")


def _top_contributors(
    ctx: PlanningContext, it: Intent, months: list[str] | None, n: int = 3
) -> tuple[str, pd.DataFrame]:
    if it.filters.get("sku"):
        bdim = "customer"
    elif it.filters.get("customer") or it.filters.get("brand") or it.filters.get("category"):
        bdim = "sku"
    else:
        bdim = "customer"
    df = run_query(ctx, SemanticQuery("consensus", bdim, it.filters, months or [], "revenue", "desc", n))
    return bdim, df


# --------------------------------------------------------------------------------------- handlers
def h_summary(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = _lang(it)
    ids = filter_ids(ctx, it.filters)
    if len(ids) == 0:
        return _no_series(ctx, it)
    tot = horizon_totals(ctx, ids, "revenue")
    m = backtest_metrics(ctx, ids)
    growth = _safe_ratio(tot.get("consensus"), tot.get("actual_ltm"))
    gb = _safe_ratio(tot.get("consensus"), tot.get("budget"))
    gt = _safe_ratio(tot.get("consensus"), tot.get("target"))
    tl = timeline(ctx, it.filters, "revenue", 24)
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    top_type = s["series_type"].value_counts() if "series_type" in s else pd.Series(dtype=int)
    answer = t(
        L,
        f"For {_scope(ctx, it)}, the consensus forecast for the next 12 months is {money(tot['consensus'], L)} "
        f"({pct(growth, L, True)} vs the last 12 months). Backtest forecast accuracy is {pct(m['accuracy'], L)} "
        f"(WMAPE {pct(m['wmape'], L)}, bias {pct(m['bias'], L, True)}). The consensus is {pct(gb, L, True)} vs "
        f"budget and {pct(gt, L, True)} vs target.",
        f"Para {_scope(ctx, it, 'art')}, o forecast de consenso dos próximos 12 meses é {money(tot['consensus'], L)} "
        f"({pct(growth, L, True)} vs últimos 12 meses). A acurácia no backtest é {pct(m['accuracy'], L)} "
        f"(WMAPE {pct(m['wmape'], L)}, viés {pct(m['bias'], L, True)}). O consenso está "
        f"{pct(gb, L, True)} vs orçamento e {pct(gt, L, True)} vs meta.",
    )
    insights = [
        t(
            L,
            f"Statistical base {money(tot['base'], L)} + commercial events {money(tot['incremental'], L)}."
            if abs(tot["incremental"]) >= 1
            else f"The whole consensus is statistical ({money(tot['base'], L)}): no commercial events.",
            f"Forecast estatístico {money(tot['base'], L)} + eventos comerciais {money(tot['incremental'], L)}."
            if abs(tot["incremental"]) >= 1
            else f"Todo o consenso é forecast estatístico ({money(tot['base'], L)}): não há eventos comerciais.",
        ),
        t(
            L,
            f"Most common demand pattern: {series_type(top_type.index[0], L)} ({int(top_type.iloc[0])} series).",
            f"Padrão de demanda mais comum: {series_type(top_type.index[0], L)} ({int(top_type.iloc[0])} séries).",
        )
        if len(top_type)
        else "",
        t(
            L,
            f"P10-P90 range for the horizon: {money(tot['p10'], L)} - {money(tot['p90'], L)}.",
            f"Faixa P10–P90 do horizonte: {money(tot['p10'], L)} a {money(tot['p90'], L)}.",
        ),
    ]
    rec = assess(ctx, it.filters, None, "revenue").get("recommendation", "")
    return _result(
        answer=answer,
        insights=[i for i in insights if i],
        metrics=[
            {
                "label": t(L, "Consensus 12M", "Consenso 12M"),
                "value": tot["consensus"],
                "format": "currency",
                "tone": "blue",
            },
            {
                "label": t(L, "Forecast accuracy", "Acurácia"),
                "value": m["accuracy"],
                "format": "percent",
                "tone": "green",
            },
            {"label": "WMAPE", "value": m["wmape"], "format": "percent", "tone": "orange"},
            {"label": t(L, "Bias", "Viés"), "value": m["bias"], "format": "percent_signed", "tone": "purple"},
            {"label": t(L, "vs Budget", "vs Orçamento"), "value": gb, "format": "percent_signed", "tone": "teal"},
            {"label": t(L, "vs Target", "vs Meta"), "value": gt, "format": "percent_signed", "tone": "navy"},
        ],
        chart={
            "type": "line",
            "title": t(L, "Revenue: actual, consensus, budget", "Receita: real, consenso e orçamento"),
            "format": "currency",
            "x": _x_months(tl["date"], L),
            "series": [
                {"name": t(L, "Actual", "Real"), "data": tl["actual"].tolist()},
                {
                    "name": t(L, "Consensus", "Consenso"),
                    "data": tl.get("consensus", pd.Series(dtype=float)).tolist(),
                },
                {
                    "name": t(L, "Budget", "Orçamento"),
                    "data": tl.get("budget", pd.Series(dtype=float)).tolist(),
                    "dashed": True,
                },
            ],
        },
        recommendations=[rec] if rec else [],
        filters=it.filters,
        facts={
            "consensus_12m": tot["consensus"],
            "statistical_12m": tot["base"],
            "events_12m": tot["incremental"],
            "actual_ltm": tot["actual_ltm"],
            "growth_vs_ltm": growth,
            "accuracy": m["accuracy"],
            "wmape": m["wmape"],
            "bias": m["bias"],
            "vs_budget": gb,
            "vs_target": gt,
            "p10": tot["p10"],
            "p90": tot["p90"],
        },
        query=f"horizon_totals(revenue, filters={it.filters}) + backtest_metrics",
    )


def h_forecast_value(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    """How much will we sell: consensus / statistical totals, P10-P90, budget, target, vs last year."""
    L = _lang(it)
    ids = filter_ids(ctx, it.filters)
    if len(ids) == 0:
        return _no_series(ctx, it)
    req = pd.DatetimeIndex(sorted({pd.Timestamp(m) for m in it.months})) if it.months else ctx.future_dates
    fut = req[req.isin(ctx.future_dates)]
    past = req[req <= ctx.last_actual]
    note = ""
    if len(fut) == 0 and len(past) == 0:
        note = t(
            L,
            "The requested months are beyond the forecast horizon; showing the full horizon instead.",
            "Os meses pedidos estão além do horizonte do forecast; mostrando o horizonte completo.",
        )
        req, fut = ctx.future_dates, ctx.future_dates
    months_all = past.append(fut)
    pmonths = [d.strftime("%Y-%m-01") for d in months_all] if it.months and not note else None
    period = period_text(pmonths, L)  # English text
    period_title = period_prep(pmonths, L, "")  # chart titles
    scope, _scope_art = _scope(ctx, it), _scope(ctx, it, "art")

    act = ctx.actuals[ctx.actuals["series_id"].isin(ids)]
    rev = horizon_totals(ctx, ids, "revenue", fut) if len(fut) else {}
    un = horizon_totals(ctx, ids, "units", fut) if len(fut) else {}
    cons, base, inc = rev.get("consensus", 0.0), rev.get("base", 0.0), rev.get("incremental", 0.0)
    cons_units = un.get("consensus", 0.0)
    p10, p90 = rev.get("consensus_p10"), rev.get("consensus_p90")
    past_rev = float(act.loc[act["date"].isin(past), "revenue"].sum())
    past_units = float(act.loc[act["date"].isin(past), "units"].sum())
    ly = float(act.loc[act["date"].isin(months_all - pd.DateOffset(years=1)), "revenue"].sum())
    landing = cons + past_rev
    vs_ly = _safe_ratio(landing, ly)
    plan = ctx.plan[ctx.plan["series_id"].isin(ids) & ctx.plan["date"].isin(months_all)] if not ctx.plan.empty else None
    budget = float(plan["budget_revenue"].sum()) if plan is not None and len(plan) else None
    target = float(plan["target_revenue"].sum()) if plan is not None and len(plan) else None
    gb, gt = _safe_ratio(landing, budget), _safe_ratio(landing, target)

    tl = timeline(ctx, it.filters, "revenue", 36).set_index("date")

    def at(d: pd.Timestamp, col: str) -> float | None:
        if col not in tl or d not in tl.index:
            return None
        v = tl.at[d, col]
        return None if pd.isna(v) else float(v)

    ly_col = [at(d - pd.DateOffset(years=1), "actual") for d in months_all]

    # Backtest view for closed months ("quanto vendemos em março?").
    bt_rev = None
    if len(past):
        bt = ctx.backtest[ctx.backtest["series_id"].isin(ids) & ctx.backtest["date"].isin(past)]
        if len(bt):
            bt = bt.merge(ctx.series[["series_id", "price"]], on="series_id")
            bt_rev = float((bt["forecast"] * bt["price"]).sum())

    plan_txt_en = (
        f" Budget {money(budget, L)} ({pct(gb, L, True)}); target {money(target, L)} ({pct(gt, L, True)})."
        if budget
        else ""
    )
    plan_txt_pt = (
        f" Orçamento: {money(budget, L)} ({pct(gb, L, True)}); meta: {money(target, L)} ({pct(gt, L, True)})."
        if budget
        else ""
    )
    if abs(inc) >= 1:
        events_en = f"statistical forecast {money(base, L)} plus commercial events {money(inc, L)}"
        events_pt = f"forecast estatístico de {money(base, L)} e eventos comerciais de {money(inc, L)}"
    else:
        events_en = "all statistical forecast, no commercial events"
        events_pt = "integralmente forecast estatístico, sem eventos comerciais no período"
    ly_txt_en = f" Change vs the same period last year: {pct(vs_ly, L, True)} ({money(ly, L)})." if ly else ""
    ly_txt_pt = f" Vs o mesmo período do ano anterior: {pct(vs_ly, L, True)} ({money(ly, L)})." if ly else ""
    if len(fut) and not len(past):
        answer = t(
            L,
            f"The consensus forecast for {period} ({scope}) is {money(cons, L)} ({units(cons_units, L)}): "
            + events_en
            + f". P10-P90 range: {money(p10, L)} to "
            f"{money(p90, L)}." + ly_txt_en + plan_txt_en,
            f"A previsão de consenso {period_prep(pmonths, L, 'para')} ({scope}) é de {money(cons, L)} ({units(cons_units, L)}): "
            + events_pt
            + ". Faixa P10–P90: "
            f"{money(p10, L)} a {money(p90, L)}." + ly_txt_pt + plan_txt_pt,
        )
    elif len(past) and not len(fut):
        bt_en = (
            f" The backtest forecast for the period was {money(bt_rev, L)} (error {pct(_safe_ratio(bt_rev, past_rev), L, True)})."
            if bt_rev
            else ""
        )
        bt_pt = (
            f" O forecast do backtest para o período era de {money(bt_rev, L)} "
            f"(desvio de {pct(_safe_ratio(bt_rev, past_rev), L, True)})."
            if bt_rev
            else ""
        )
        answer = t(
            L,
            f"In {period} ({scope}) actual sales were {money(past_rev, L)} ({units(past_units, L)}), "
            f"{pct(vs_ly, L, True)} vs the same period last year ({money(ly, L)})." + bt_en + plan_txt_en,
            f"{_cap(period_prep(pmonths, L, 'em'))} ({scope}) as vendas realizadas foram de {money(past_rev, L)} ({units(past_units, L)}), "
            f"{pct(vs_ly, L, True)} vs o mesmo período do ano anterior ({money(ly, L)})." + bt_pt + plan_txt_pt,
        )
    else:
        answer = t(
            L,
            f"For {period} ({scope}) the landing estimate is {money(landing, L)}: {money(past_rev, L)} already sold "
            f"through {month_name(ctx.last_actual, L)} plus {money(cons, L)} of consensus forecast for the open months "
            f"(P10-P90 {money(p10, L)} to {money(p90, L)})." + ly_txt_en + plan_txt_en,
            f"{_cap(period_prep(pmonths, L, 'para'))} ({scope}) a estimativa de fechamento é de {money(landing, L)}: {money(past_rev, L)} já "
            f"realizados até {month_name(ctx.last_actual, L)} + {money(cons, L)} de forecast de consenso para os "
            f"meses em aberto (P10–P90 {money(p10, L)} a {money(p90, L)})." + ly_txt_pt + plan_txt_pt,
        )

    insights: list[str] = [note] if note else []
    if len(fut) > 1 and "consensus" in tl:
        monthly = tl.loc[tl.index.isin(fut), "consensus"]
        if len(monthly):
            peak = monthly.idxmax()
            insights.append(
                t(
                    L,
                    f"Peak month: {month_name(peak, L)} ({money(monthly.max(), L)}).",
                    f"Mês de maior venda: {month_name(peak, L)} ({money(monthly.max(), L)}).",
                )
            )
    if len(fut):
        bdim, top = _top_contributors(ctx, it, [d.strftime("%Y-%m-01") for d in fut])
        if len(top):
            lst = "; ".join(f"{_label(ctx, bdim, r.member)} ({money(r.consensus, L)})" for r in top.itertuples())
            insights.append(
                t(
                    L,
                    f"Largest {dim_label(bdim, L, True)} in the forecast: {lst}.",
                    f"Maiores {dim_label(bdim, L, True)} no forecast: {lst}.",
                )
            )
        if inc and cons:
            insights.append(
                t(
                    L,
                    f"Commercial events account for {pct(inc / cons, L)} of the consensus.",
                    f"Os eventos comerciais respondem por {pct(inc / cons, L)} do consenso.",
                )
            )

    if len(fut) and not len(past):
        metrics = [
            {"label": t(L, "Consensus", "Consenso"), "value": cons, "format": "currency", "tone": "blue"},
            {"label": t(L, "Units", "Unidades"), "value": cons_units, "format": "units", "tone": "navy"},
            {
                "label": t(L, "Statistical forecast", "Forecast estatístico"),
                "value": base,
                "format": "currency",
                "tone": "purple",
            },
            {
                "label": t(L, "vs last year", "vs ano anterior"),
                "value": vs_ly,
                "format": "percent_signed",
                "tone": "teal",
            },
            {"label": t(L, "vs Budget", "vs Orçamento"), "value": gb, "format": "percent_signed", "tone": "green"},
            {"label": t(L, "vs Target", "vs Meta"), "value": gt, "format": "percent_signed", "tone": "orange"},
        ]
    elif len(past) and not len(fut):
        metrics = [
            {"label": t(L, "Actual", "Realizado"), "value": past_rev, "format": "currency", "tone": "blue"},
            {"label": t(L, "Units", "Unidades"), "value": past_units, "format": "units", "tone": "navy"},
            {
                "label": t(L, "vs last year", "vs ano anterior"),
                "value": vs_ly,
                "format": "percent_signed",
                "tone": "teal",
            },
            {
                "label": t(L, "Backtest forecast", "Forecast do backtest"),
                "value": bt_rev,
                "format": "currency",
                "tone": "purple",
            },
            {"label": t(L, "vs Budget", "vs Orçamento"), "value": gb, "format": "percent_signed", "tone": "green"},
            {"label": t(L, "vs Target", "vs Meta"), "value": gt, "format": "percent_signed", "tone": "orange"},
        ]
    else:
        metrics = [
            {
                "label": t(L, "Landing estimate", "Estimativa de fechamento"),
                "value": landing,
                "format": "currency",
                "tone": "blue",
            },
            {"label": t(L, "Actual to date", "Realizado"), "value": past_rev, "format": "currency", "tone": "navy"},
            {
                "label": t(L, "Consensus (open months)", "Consenso (meses em aberto)"),
                "value": cons,
                "format": "currency",
                "tone": "purple",
            },
            {
                "label": t(L, "vs last year", "vs ano anterior"),
                "value": vs_ly,
                "format": "percent_signed",
                "tone": "teal",
            },
            {"label": t(L, "vs Budget", "vs Orçamento"), "value": gb, "format": "percent_signed", "tone": "green"},
            {"label": t(L, "vs Target", "vs Meta"), "value": gt, "format": "percent_signed", "tone": "orange"},
        ]

    if len(months_all) >= 3:
        chart = {
            "type": "line",
            "format": "currency",
            "title": t(L, f"Revenue by month - {period}", f"Receita por mês – {period_title}"),
            "x": _x_months(months_all, L),
            "series": [
                {
                    "name": t(L, "Actual", "Real"),
                    "data": [at(d, "actual") if d <= ctx.last_actual else None for d in months_all],
                },
                {"name": t(L, "Consensus", "Consenso"), "data": [at(d, "consensus") for d in months_all]},
                {"name": t(L, "Last year", "Ano anterior"), "data": ly_col, "dashed": True},
                {"name": t(L, "Budget", "Orçamento"), "data": [at(d, "budget") for d in months_all], "dashed": True},
                {"name": t(L, "Target", "Meta"), "data": [at(d, "target") for d in months_all], "dashed": True},
            ],
        }
    elif len(fut):
        chart = {
            "type": "bar",
            "format": "currency",
            "title": t(L, f"Forecast range - {period}", f"Faixa do forecast – {period_title}"),
            "x": [
                t(L, "Last year", "Ano anterior"),
                "P10",
                t(L, "Statistical", "Estatístico"),
                t(L, "Consensus", "Consenso"),
                "P90",
                t(L, "Budget", "Orçamento"),
                t(L, "Target", "Meta"),
            ],
            "series": [{"name": t(L, "Value", "Valor"), "data": [ly or None, p10, base, cons, p90, budget, target]}],
            "highlight": 3,
        }
    else:
        chart = {
            "type": "bar",
            "format": "currency",
            "title": t(L, f"Actual vs forecast - {period}", f"Real vs forecast – {period_title}"),
            "x": [
                t(L, "Last year", "Ano anterior"),
                t(L, "Backtest forecast", "Forecast do backtest"),
                t(L, "Actual", "Real"),
            ],
            "series": [{"name": t(L, "Value", "Valor"), "data": [ly or None, bt_rev, past_rev]}],
            "highlight": 2,
        }

    rows = []
    for d in months_all:
        rows.append(
            [
                month_short(d, L),
                at(d, "actual") if d <= ctx.last_actual else None,
                at(d, "consensus"),
                at(d, "base"),
                at(d, "p10"),
                at(d, "p90"),
                at(d, "budget"),
                at(d, "target"),
                at(d - pd.DateOffset(years=1), "actual"),
            ]
        )
    recs = []
    if not len(fut):
        if gt is not None and gt < -0.02:
            recs.append(
                t(
                    L,
                    f"Actual sales landed {pct(gt, L, True)} vs the target: review the causes (stock-outs, lost "
                    "distribution, events that did not happen) before committing the next targets.",
                    f"O realizado ficou {pct(gt, L, True)} vs a meta: revise as causas (rupturas, perda de "
                    "distribuição, eventos que não aconteceram) antes de comprometer as próximas metas.",
                )
            )
        recs.append(
            t(
                L,
                "Use the Model Performance page to see which series drove the deviation vs the backtest forecast.",
                "Use a página Modelos para ver quais séries explicam o desvio vs o forecast do backtest.",
            )
        )
    elif gt is not None and gt < -0.02:
        recs.append(
            t(
                L,
                f"The forecast is {pct(-gt, L)} below target: test levers in a what-if simulation or review the target.",
                f"O forecast está {pct(-gt, L)} abaixo da meta: teste alavancas numa simulação what-if ou revise a meta.",
            )
        )
    elif gb is not None and gb < -0.02:
        recs.append(
            t(
                L,
                "The forecast is below budget: bring the gap to the S&OP pre-meeting with a recovery plan.",
                "O forecast está abaixo do orçamento: leve o gap para a pré-reunião de S&OP com um plano de recuperação.",
            )
        )
    if len(fut):
        recs.append(
            t(
                L,
                "Validate the commercial events behind the consensus with Key Accounts before the S&OP meeting.",
                "Valide com os Key Accounts (KAM) os eventos comerciais por trás do consenso antes da reunião de S&OP.",
            )
        )
    return _result(
        answer=answer,
        insights=insights,
        metrics=metrics,
        chart=chart,
        table={
            "columns": [
                t(L, "Month", "Mês"),
                t(L, "Actual", "Real"),
                t(L, "Consensus", "Consenso"),
                t(L, "Statistical", "Estatístico"),
                "P10",
                "P90",
                t(L, "Budget", "Orçamento"),
                t(L, "Target", "Meta"),
                t(L, "Last year", "Ano anterior"),
            ],
            "rows": rows,
            "formats": ["text"] + ["currency"] * 8,
        },
        recommendations=recs,
        filters=it.filters,
        facts={
            "months": [d.strftime("%Y-%m") for d in months_all],
            "consensus": cons,
            "consensus_units": cons_units,
            "statistical": base,
            "events": inc,
            "p10": p10,
            "p90": p90,
            "actual": past_rev,
            "actual_units": past_units,
            "landing": landing,
            "last_year": ly,
            "vs_last_year": vs_ly,
            "budget": budget,
            "target": target,
            "vs_budget": gb,
            "vs_target": gt,
            "backtest_forecast": bt_rev,
        },
        query=(
            f"SELECT consensus, statistical, p10, p90, budget, target, actual_ly (revenue) "
            f"WHERE {it.filters or 'todos'} PERIOD {', '.join(d.strftime('%Y-%m') for d in months_all)}"
        ),
    )


METRIC_LABEL = {
    "wmape": ("WMAPE", "WMAPE"),
    "accuracy": ("Accuracy", "Acurácia"),
    "bias": ("Bias", "Viés"),
    "mae": ("MAE", "MAE"),
    "rmse": ("RMSE", "RMSE"),
    "smape": ("sMAPE", "sMAPE"),
    "mase": ("MASE", "MASE"),
}


def _metric_format(metric: str) -> str:
    if metric in ("wmape", "accuracy", "smape"):
        return "percent"
    return "percent_signed" if metric == "bias" else "number"


def h_metric_lookup(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    """Value of an accuracy metric for an entity (or the portfolio), with context and ranking."""
    L = _lang(it)
    metric = it.metric if it.metric in METRIC_LABEL else "wmape"
    mlabel = METRIC_LABEL[metric][0 if L == "en" else 1]
    ids = filter_ids(ctx, it.filters)
    if len(ids) == 0:
        return _no_series(ctx, it)
    m = _bt_metrics(ctx, ids, it.months or None)
    if m["wmape"] is None:
        return _no_backtest(ctx, it)
    rank_dim = next((d for d in SPECIFICITY if it.filters.get(d) and not isinstance(it.filters[d], list)), None)
    ref_filters = {k: v for k, v in it.filters.items() if k != rank_dim} if rank_dim else {}
    ref = _bt_metrics(ctx, filter_ids(ctx, ref_filters), it.months or None)
    ref_label = (
        t(L, "the total portfolio", "o portfólio total")
        if not ref_filters
        else ", ".join(_value_text(ctx, k, v) for k, v in ref_filters.items())
    )
    peer_dim = rank_dim or (it.dimension if it.dimension in RANK_DIMS else "customer")
    qmetric = metric if metric in ("wmape", "accuracy", "bias") else "wmape"
    peers = run_query(
        ctx,
        SemanticQuery(qmetric, peer_dim, ref_filters if rank_dim else it.filters, it.months, "units", "desc", 500),
    )
    total_vol = peers["volume"].sum() if len(peers) else 0
    peers = peers[peers["volume"] >= 0.002 * max(total_vol, 1)] if len(peers) else peers

    pos_txt_en = pos_txt_pt = ""
    pos = None
    if rank_dim and len(peers):
        if metric == "bias":
            ordered = peers.sort_values("bias", ascending=m["bias"] < 0)
        else:
            ordered = peers.sort_values("wmape", ascending=True)
        names = list(ordered["member"])
        if it.filters[rank_dim] in names:
            pos = names.index(it.filters[rank_dim]) + 1
            n = len(names)
            dpl = dim_label(peer_dim, L, True)
            if metric == "bias":
                sign_en = "positive" if m["bias"] >= 0 else "negative"
                sign_pt = "positivo" if m["bias"] >= 0 else "negativo"
                pos_txt_en = f" Among {n} {dpl} it has the {ordinal(pos, L)} largest {sign_en} bias."
                pos_txt_pt = f" Entre {n} {dpl}, é o {ordinal(pos, L)} maior viés {sign_pt}."
            else:
                pos_txt_en = f" It ranks {ordinal(pos, L)} of {n} {dpl} on accuracy (1st = lowest error)."
                pos_txt_pt = f" No ranking de acurácia fica em {ordinal(pos, L)} de {n} {dpl} (1º = menor erro)."

    w, b, acc = m["wmape"], m["bias"], m["accuracy"]
    bias_state_en = "over-forecast" if b > 0.05 else "under-forecast" if b < -0.05 else "balanced"
    bias_state_pt = "superestimado" if b > 0.05 else "subestimado" if b < -0.05 else "equilibrado"
    # "qual o viés da Vila Verde em dezembro?" -> "O viés do cliente Vila Verde Mercados em dezembro/2025 é ..."
    scope_de = _scope(ctx, it, "de") + (f" {period_prep(it.months, L, 'em')}" if it.months else "")
    scope_en = _scope(ctx, it) + (f" in {period_text(it.months, L)}" if it.months else "")
    if metric == "wmape":
        lead_en = f"WMAPE for {scope_en} is {pct(w, L)} (accuracy {pct(acc, L)}, bias {pct(b, L, True)})"
        lead_pt = f"O WMAPE {scope_de} é {pct(w, L)} (acurácia {pct(acc, L)}, viés {pct(b, L, True)})"
        ref_val = ref["wmape"]
    elif metric == "accuracy":
        lead_en = f"Forecast accuracy for {scope_en} is {pct(acc, L)} (WMAPE {pct(w, L)}, bias {pct(b, L, True)})"
        lead_pt = f"A acurácia {scope_de} é {pct(acc, L)} (WMAPE {pct(w, L)}, viés {pct(b, L, True)})"
        ref_val = ref["accuracy"]
    elif metric == "bias":
        lead_en = f"Bias for {scope_en} is {pct(b, L, True)} - {bias_state_en} (±5% band), with WMAPE {pct(w, L)}"
        lead_pt = f"O viés {scope_de} é {pct(b, L, True)} – {bias_state_pt} (faixa de ±5%), com WMAPE de {pct(w, L)}"
        ref_val = ref["bias"]
    elif metric == "mase":
        lead_en = f"Median MASE for {scope_en} is {dec(m['mase'], L)} (below 1 = better than the naive benchmark)"
        lead_pt = (
            f"O MASE mediano {scope_de} é {dec(m['mase'], L)} (abaixo de 1 = melhor que a referência ingênua); "
            f"WMAPE de {pct(w, L)}"
        )
        ref_val = ref["mase"]
    else:
        lead_en = f"{mlabel} for {scope_en} is {num(m[metric], L, 1) if metric != 'smape' else pct(m[metric], L)}"
        lead_pt = (
            f"O {mlabel} {scope_de} é "
            f"{num(m[metric], L, 1) + ' unidades' if metric != 'smape' else pct(m[metric], L)} "
            f"(WMAPE {pct(w, L)}, viés {pct(b, L, True)})"
        )
        ref_val = ref.get(metric)

    def fmt(v: float | None) -> str:
        if metric in ("wmape", "accuracy", "smape"):
            return pct(v, L)
        if metric == "bias":
            return pct(v, L, True)
        if metric == "mase":
            return dec(v, L)
        return f"{num(v, L, 1)} {t(L, 'units', 'unidades')}"

    cmp_en = f", vs {fmt(ref_val)} for {ref_label}." if (it.filters and ref_val is not None) else "."
    cmp_pt = "."
    if it.filters and ref_val is not None:
        cmp_pt = f", contra {fmt(ref_val)} " + (f"em {ref_label}." if ref_filters else "no portfólio total.")
    if not it.filters:
        cmp_en = f" in the rolling-origin backtest of {m['series']} series."
        cmp_pt = f" no backtest com origem móvel de {m['series']} séries."
    answer = t(L, lead_en + cmp_en + pos_txt_en, lead_pt + cmp_pt + pos_txt_pt)

    # Peers chart / table (entity highlighted).
    show = peers.copy()
    if len(show):
        show = show.sort_values(qmetric, ascending=qmetric != "accuracy" if qmetric != "bias" else False)
        if rank_dim and it.filters[rank_dim] in list(show["member"]):
            head = show.head(12)
            if it.filters[rank_dim] not in list(head["member"]):
                head = pd.concat([head.head(11), show[show["member"] == it.filters[rank_dim]]])
            show = head
        else:
            show = show.head(12)
    names = [_label(ctx, peer_dim, x) for x in show["member"]] if len(show) else []
    highlight = (
        list(show["member"]).index(it.filters[rank_dim])
        if rank_dim and len(show) and it.filters[rank_dim] in list(show["member"])
        else None
    )
    insights = []
    if not it.filters and len(show):
        best = peers.sort_values("wmape").iloc[0]
        worst = peers.sort_values("wmape").iloc[-1]
        insights.append(
            t(
                L,
                f"Best {dim_label(peer_dim, L)}: {_label(ctx, peer_dim, best['member'])} (WMAPE {pct(best['wmape'], L)}); "
                f"worst: {_label(ctx, peer_dim, worst['member'])} ({pct(worst['wmape'], L)}).",
                f"Melhor {dim_label(peer_dim, L)}: {_label(ctx, peer_dim, best['member'])} (WMAPE {pct(best['wmape'], L)}); "
                f"pior: {_label(ctx, peer_dim, worst['member'])} ({pct(worst['wmape'], L)}).",
            )
        )
    insights.append(
        t(
            L,
            f"Backtest over {m['series']} series and {num(m['volume'], L)} units of actual demand.",
            f"Backtest de {m['series']} séries e {num(m['volume'], L)} unidades de demanda real.",
        )
    )
    if m.get("mase") is not None and metric != "mase":
        insights.append(t(L, f"Median MASE: {dec(m['mase'], L)}.", f"MASE mediano: {dec(m['mase'], L)}."))

    recs = []
    if ref["wmape"] and w > 1.2 * ref["wmape"]:
        recs.append(
            t(
                L,
                "Error is well above the reference: check outliers and stock-outs in the history and confirm the "
                "demand pattern with Sales.",
                "Erro bem acima da referência: verifique outliers e rupturas no histórico e confirme o padrão de "
                "demanda com Vendas.",
            )
        )
    if abs(b) > 0.05:
        recs.append(
            t(
                L,
                f"Bias beyond ±5% ({bias_state_en}): recalibrate the base level and review recent overrides.",
                f"Viés além de ±5% ({bias_state_pt}): recalibre o patamar da base e revise os ajustes comerciais recentes.",
            )
        )
    if not recs:
        recs.append(
            t(
                L,
                "Performance is in line with the reference: keep the statistical forecast with low touch.",
                "Desempenho em linha com a referência: mantenha o forecast estatístico com baixa intervenção.",
            )
        )
    metrics = [
        {"label": mlabel, "value": m[metric], "format": _metric_format(metric), "tone": "blue"},
    ]
    for code, fmt_, tone in (
        ("wmape", "percent", "orange"),
        ("accuracy", "percent", "green"),
        ("bias", "percent_signed", "purple"),
    ):
        if code != metric:
            metrics.append(
                {"label": METRIC_LABEL[code][0 if L == "en" else 1], "value": m[code], "format": fmt_, "tone": tone}
            )
    if it.filters and ref_val is not None:
        metrics.append(
            {
                "label": t(L, f"{mlabel} - reference", f"{mlabel} – referência"),
                "value": ref_val,
                "format": _metric_format(metric),
                "tone": "teal",
            }
        )
    if pos is not None:
        metrics.append(
            {
                "label": t(L, "Ranking position", "Posição no ranking"),
                "value": f"{ordinal(pos, L)} / {len(peers)}",
                "format": "text",
                "tone": "navy",
            }
        )
    chart_fmt = "percent_signed" if qmetric == "bias" else "percent"
    qlabel = METRIC_LABEL[qmetric][0 if L == "en" else 1]
    return _result(
        answer=answer,
        insights=insights,
        metrics=metrics,
        chart={
            "type": "bar",
            "horizontal": True,
            "format": chart_fmt,
            "title": t(L, f"{qlabel} by {dim_label(peer_dim, L)}", f"{qlabel} por {dim_label(peer_dim, L)}"),
            "x": names,
            "series": [{"name": qlabel, "data": show[qmetric].tolist() if len(show) else []}],
            **({"highlight": highlight} if highlight is not None else {}),
        }
        if len(show)
        else None,
        table={
            "columns": [dim_title(peer_dim, L), "WMAPE", t(L, "Accuracy", "Acurácia"), t(L, "Bias", "Viés"), "Volume"],
            "rows": [
                [n_, w_, a_, b_, v_]
                for n_, w_, a_, b_, v_ in zip(
                    names, show["wmape"], show["accuracy"], show["bias"], show["volume"], strict=True
                )
            ],
            "formats": ["text", "percent", "percent", "percent_signed", "units"],
        }
        if len(show)
        else None,
        recommendations=recs,
        filters=it.filters,
        facts={
            "metric": metric,
            "value": m.get(metric),
            "wmape": w,
            "accuracy": acc,
            "bias": b,
            "mae": m["mae"],
            "rmse": m["rmse"],
            "smape": m["smape"],
            "mase": m["mase"],
            "series": m["series"],
            "reference": ref_val,
            "rank": pos,
            "peers": len(peers),
        },
        query=SemanticQuery(qmetric, peer_dim, ref_filters if rank_dim else it.filters, it.months, "units").describe(),
    )


def h_entity_overview(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    """KPIs and top risks for one customer / region / channel / category / brand / SKU."""
    if not it.filters:
        return h_summary(ctx, it)
    L = _lang(it)
    ids = filter_ids(ctx, it.filters)
    if len(ids) == 0:
        return _no_series(ctx, it)
    tot = horizon_totals(ctx, ids, "revenue")
    m = backtest_metrics(ctx, ids)
    growth = _safe_ratio(tot.get("consensus"), tot.get("actual_ltm"))
    gb = _safe_ratio(tot.get("consensus"), tot.get("budget"))
    gt = _safe_ratio(tot.get("consensus"), tot.get("target"))
    alerts = _alerts_for(ctx, it.filters)
    sev = {k: sum(1 for a in alerts if a["severity"] == k) for k in ("critical", "high", "medium", "low")}
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    plain = _scope(ctx, it)
    head = plain[:1].upper() + plain[1:]
    if alerts:
        alerts_en = f"{len(alerts)} open alerts ({sev['critical']} critical, {sev['high']} high)."
        alerts_pt = (
            f"Há {plural(len(alerts), 'alerta aberto', 'alertas abertos')} "
            f"({plural(sev['critical'], 'crítico', 'críticos')}, {plural(sev['high'], 'alto', 'altos')})."
        )
    else:
        alerts_en, alerts_pt = "No open alerts.", "Não há alertas abertos."
    answer = t(
        L,
        f"{head}: 12-month consensus forecast of {money(tot['consensus'], L)} "
        f"({pct(growth, L, True)} vs the last 12 months), {pct(gb, L, True)} vs budget and {pct(gt, L, True)} vs target. "
        f"Backtest accuracy {pct(m['accuracy'], L)} (WMAPE {pct(m['wmape'], L)}, bias {pct(m['bias'], L, True)}) "
        f"across {len(s)} series. {alerts_en}",
        f"{head}: forecast de consenso de 12 meses de {money(tot['consensus'], L)} ({pct(growth, L, True)} vs "
        f"últimos 12 meses), {pct(gb, L, True)} vs orçamento e {pct(gt, L, True)} vs meta. Acurácia no backtest de "
        f"{pct(m['accuracy'], L)} (WMAPE {pct(m['wmape'], L)}, viés {pct(m['bias'], L, True)}) em {len(s)} séries. "
        f"{alerts_pt}",
    )
    insights = []
    bdim, top = _top_contributors(ctx, it, None, 3)
    if len(top):
        lst = "; ".join(f"{_label(ctx, bdim, r.member)} ({money(r.consensus, L)})" for r in top.itertuples())
        insights.append(
            t(
                L,
                f"Largest {dim_label(bdim, L, True)} in the forecast: {lst}.",
                f"Maiores {dim_label(bdim, L, True)} no forecast: {lst}.",
            )
        )
    for a in alerts[:3]:
        insights.append(f"{a['title']} – {_alert_entity(a)} ({a['magnitude']}).")
    if "series_type" in s and len(s):
        tt = s["series_type"].value_counts()
        insights.append(
            t(
                L,
                f"Main demand pattern: {series_type(tt.index[0], L)} ({int(tt.iloc[0])} of {len(s)} series).",
                f"Padrão de demanda predominante: {series_type(tt.index[0], L)} ({int(tt.iloc[0])} de {len(s)} séries).",
            )
        )
    tl = timeline(ctx, it.filters, "revenue", 24)
    recs = list(dict.fromkeys(a["recommendation"] for a in alerts[:4] if a.get("recommendation")))[:2]
    if not recs:
        rec = assess(ctx, it.filters, None, "revenue").get("recommendation")
        if rec:
            recs.append(rec)
    return _result(
        answer=answer,
        insights=insights,
        metrics=[
            {
                "label": t(L, "Consensus 12M", "Consenso 12M"),
                "value": tot.get("consensus"),
                "format": "currency",
                "tone": "blue",
            },
            {
                "label": t(L, "vs last 12 months", "vs últimos 12 meses"),
                "value": growth,
                "format": "percent_signed",
                "tone": "teal",
            },
            {"label": t(L, "vs Budget", "vs Orçamento"), "value": gb, "format": "percent_signed", "tone": "green"},
            {"label": t(L, "vs Target", "vs Meta"), "value": gt, "format": "percent_signed", "tone": "navy"},
            {"label": t(L, "Accuracy", "Acurácia"), "value": m["accuracy"], "format": "percent", "tone": "purple"},
            {"label": t(L, "Bias", "Viés"), "value": m["bias"], "format": "percent_signed", "tone": "orange"},
            {
                "label": t(L, "Open alerts", "Alertas abertos"),
                "value": len(alerts),
                "format": "number",
                "tone": "red" if sev["critical"] else "yellow",
            },
        ],
        chart={
            "type": "line",
            "format": "currency",
            "title": t(L, f"Revenue - {_scope(ctx, it)}", f"Receita – {_scope(ctx, it)}"),
            "x": _x_months(tl["date"], L),
            "series": [
                {"name": t(L, "Actual", "Real"), "data": tl["actual"].tolist()},
                {"name": t(L, "Consensus", "Consenso"), "data": tl.get("consensus", pd.Series(dtype=float)).tolist()},
                {
                    "name": t(L, "Budget", "Orçamento"),
                    "data": tl.get("budget", pd.Series(dtype=float)).tolist(),
                    "dashed": True,
                },
                {
                    "name": t(L, "Target", "Meta"),
                    "data": tl.get("target", pd.Series(dtype=float)).tolist(),
                    "dashed": True,
                },
            ],
        },
        table={
            "columns": [
                t(L, "Alert", "Alerta"),
                t(L, "Severity", "Severidade"),
                t(L, "Entity", "Entidade"),
                "Magnitude",
                t(L, "Impact (R$)", "Impacto (R$)"),
            ],
            "rows": [
                [
                    a["title"],
                    severity(a["severity"], L).capitalize(),
                    _alert_entity(a),
                    a["magnitude"],
                    a["potential_impact"],
                ]
                for a in alerts[:8]
            ],
            "formats": ["text", "text", "text", "text", "currency"],
        }
        if alerts
        else {
            "columns": [
                dim_title(bdim, L),
                t(L, "Consensus 12M", "Consenso 12M"),
                t(L, "Gap vs budget", "Gap vs orçamento"),
            ],
            "rows": [
                [_label(ctx, bdim, r.member), r.consensus, getattr(r, "gap_vs_budget", None)] for r in top.itertuples()
            ],
            "formats": ["text", "currency", "currency"],
        },
        recommendations=recs,
        filters=it.filters,
        facts={
            "consensus_12m": tot.get("consensus"),
            "statistical_12m": tot.get("base"),
            "actual_ltm": tot.get("actual_ltm"),
            "growth_vs_ltm": growth,
            "budget_12m": tot.get("budget"),
            "target_12m": tot.get("target"),
            "vs_budget": gb,
            "vs_target": gt,
            "accuracy": m["accuracy"],
            "wmape": m["wmape"],
            "bias": m["bias"],
            "series": len(s),
            "alerts": sev | {"total": len(alerts)},
            "top_alerts": [{k: a[k] for k in ("title", "entity", "magnitude", "potential_impact")} for a in alerts[:5]],
            "top_contributors": {_label(ctx, bdim, r.member): r.consensus for r in top.itertuples()},
        },
        query=f"entity_overview(filters={it.filters}): horizon_totals + backtest_metrics + alerts",
    )


def _no_backtest(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = _lang(it)
    when_en = f" in {period_text(it.months, 'en')}" if it.months else ""
    when_pt = f" {period_prep(it.months, 'pt', 'em')}" if it.months else ""
    return _result(
        answer=t(
            L,
            f"There are no backtest results for {_scope(ctx, it)}{when_en}. Accuracy and bias are measured on "
            "closed months of the rolling-origin backtest.",
            f"Não há resultados de backtest para {_scope(ctx, it, 'art')}{when_pt}. Acurácia e viés são medidos "
            "nos meses já fechados do backtest com origem móvel.",
        ),
        filters=it.filters,
    )


def h_accuracy(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = _lang(it)
    dim = it.dimension if it.dimension in RANK_DIMS else "sku"
    worst = it.direction != "best"
    q = SemanticQuery("wmape", dim, it.filters, it.months, "units", "desc" if worst else "asc", 25)
    df = run_query(ctx, q)
    if df.empty:
        return _no_backtest(ctx, it)
    total_vol = df["volume"].sum()
    df = df[df["volume"] >= 0.002 * max(total_vol, 1)].head(8)
    overall = _bt_metrics(ctx, filter_ids(ctx, it.filters), it.months or None)
    names = [_label(ctx, dim, m) for m in df["member"]]
    lst = "; ".join(f"{n} (WMAPE {pct(w, L)})" for n, w in zip(names[:3], df["wmape"][:3], strict=False))
    dl = dim_label(dim, L, True)
    when_en = f" in {period_text(it.months, L)}" if it.months else ""
    when_pt = f" {period_prep(it.months, L, 'em')}" if it.months else ""
    answer = t(
        L,
        f"The {dl} with the {'worst' if worst else 'best'} forecast accuracy{when_en} "
        f"({'highest' if worst else 'lowest'} WMAPE first) are: {lst}. "
        f"Overall WMAPE for {_scope(ctx, it)} is {pct(overall['wmape'], L)} (accuracy {pct(overall['accuracy'], L)}).",
        f"{article_pl(dim, L)} {dl} com {'pior' if worst else 'melhor'} acurácia{when_pt} são: {lst}. "
        f"O WMAPE geral {_scope(ctx, it, 'de')} é {pct(overall['wmape'], L)} (acurácia {pct(overall['accuracy'], L)}).",
    )
    insights = []
    if dim == "sku" and len(df) and "series_type" in ctx.series:
        types = ctx.series[ctx.series["sku"].isin(df["member"])]["series_type"].value_counts()
        insights.append(
            t(
                L,
                f"Dominant demand patterns among them: {', '.join(series_type(x, L) for x in types.index[:3])}.",
                f"Padrões de demanda predominantes: {', '.join(series_type(x, L) for x in types.index[:3])}.",
            )
        )
    share = df["volume"].sum() / total_vol if total_vol else None
    if share is not None:
        insights.append(
            t(
                L,
                f"They represent {pct(share, L)} of the evaluated volume.",
                f"{'Elas' if dim in FEMININE else 'Eles'} representam {pct(share, L)} do volume avaliado.",
            )
        )
    recs = (
        [
            t(
                L,
                "Check outliers and stock-outs in the history of these items, and confirm the demand pattern "
                "with Sales.",
                "Verifique outliers e rupturas no histórico desses itens e confirme o padrão de demanda com Vendas.",
            ),
            t(
                L,
                "For intermittent items, plan with safety stock rather than point-forecast precision.",
                "Para itens intermitentes, planeje com estoque de segurança em vez de precisão pontual.",
            ),
        ]
        if worst
        else [
            t(
                L,
                "Use these as low-touch items: automate the statistical forecast.",
                "Use-os como itens de baixa intervenção: automatize o forecast estatístico.",
            )
        ]
    )
    return _result(
        answer=answer,
        insights=insights,
        metrics=[
            {
                "label": t(L, "Overall WMAPE", "WMAPE geral"),
                "value": overall["wmape"],
                "format": "percent",
                "tone": "orange",
            },
            {
                "label": t(L, "Overall accuracy", "Acurácia geral"),
                "value": overall["accuracy"],
                "format": "percent",
                "tone": "green",
            },
            {
                "label": t(L, f"{_cap(dl)} listed", f"{_cap(dl)} {agree('listados', dim, L)}"),
                "value": len(df),
                "format": "number",
                "tone": "blue",
            },
        ],
        chart={
            "type": "bar",
            "horizontal": True,
            "format": "percent",
            "title": t(L, f"WMAPE by {dim_label(dim, L)}", f"WMAPE por {dim_label(dim, L)}"),
            "x": names,
            "series": [{"name": "WMAPE", "data": df["wmape"].tolist()}],
        },
        table={
            "columns": [dim_title(dim, L), "WMAPE", t(L, "Accuracy", "Acurácia"), t(L, "Bias", "Viés"), "Volume"],
            "rows": [
                [n, w, a, b, v]
                for n, w, a, b, v in zip(names, df["wmape"], df["accuracy"], df["bias"], df["volume"], strict=True)
            ],
            "formats": ["text", "percent", "percent", "percent_signed", "units"],
        },
        recommendations=recs,
        filters=it.filters,
        facts={
            "overall_wmape": overall["wmape"],
            "overall_accuracy": overall["accuracy"],
            "ranking": [
                {"name": n, "wmape": w, "bias": b} for n, w, b in zip(names, df["wmape"], df["bias"], strict=True)
            ],
        },
        query=q.describe(),
    )


def h_bias(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = _lang(it)
    dim = it.dimension if it.dimension in RANK_DIMS else "customer"
    mode = it.direction if it.direction in ("over", "under", "abs") else "over"
    over = mode != "under"
    q = SemanticQuery("bias", dim, it.filters, it.months, "units", "asc" if mode == "under" else "desc", 50)
    df = run_query(ctx, q)
    if df.empty:
        return _no_backtest(ctx, it)
    if mode == "abs":
        df = df.reindex(df["bias"].abs().sort_values(ascending=False).index)
        flagged = df["bias"].abs() > 0.05
    else:
        flagged = df["bias"] > 0.05 if over else df["bias"] < -0.05
    sel = df[flagged].head(10)
    dl = dim_label(dim, L, True)
    art = article_pl(dim, L)
    state_pt = {"over": "superestimados", "under": "subestimados", "abs": "com viés acima de ±5%"}[mode]
    state_en = {"over": "over-forecasted", "under": "under-forecasted", "abs": "biased beyond ±5%"}[mode]
    bt_pt = f"no backtest {period_prep(it.months, L, 'de')}" if it.months else "no backtest"
    bt_en = f"in the {period_text(it.months, L)} backtest" if it.months else "in the backtest"
    if sel.empty:
        sel = df.head(5)
        names = [_label(ctx, dim, m) for m in sel["member"]]
        lst = "; ".join(f"{n} ({pct(b, L, True)})" for n, b in zip(names[:3], sel["bias"][:3], strict=False))
        fem = dim in FEMININE
        if mode == "abs":
            none_pt = f"{none_of(dim, L)} ultrapassa o limite de ±5% de viés. Os maiores vieses (em módulo) são"
            none_en = f"No {dim_label(dim, L)} exceeds the ±5% bias threshold. The largest absolute biases are"
        else:
            word = ("superestimad" if over else "subestimad") + ("a" if fem else "o")
            rule = "> +5%" if over else "< -5%"
            none_pt = (
                f"{none_of(dim, L)} está {word} (viés {rule} {bt_pt}). "
                f"{art} de viés mais {'alto' if over else 'baixo'} são"
            )
            none_en = (
                f"No {dim_label(dim, L)} is {'over' if over else 'under'}-forecasted (bias {rule} {bt_en}). "
                f"The {'highest' if over else 'lowest'} biases are"
            )
        answer = t(L, f"{none_en}: {lst}.", f"{none_pt}: {lst}.")
    else:
        names = [_label(ctx, dim, m) for m in sel["member"]]
        lst = "; ".join(f"{n} ({pct(b, L, True)})" for n, b in zip(names[:4], sel["bias"][:4], strict=False))
        rule_pt = {"over": "> +5%", "under": "< -5%", "abs": "além de ±5%"}[mode]
        rule_en = {"over": "> +5%", "under": "< -5%", "abs": "beyond ±5%"}[mode]
        state_agreed = agree(state_pt, dim, L) if mode != "abs" else state_pt
        answer = t(
            L,
            f"{len(sel)} {dl} are {state_en} (bias {rule_en} {bt_en}): {lst}.",
            f"{len(sel)} {dl} estão {state_agreed} (viés {rule_pt} {bt_pt}): {lst}.",
        )
    return _result(
        answer=answer,
        insights=[
            t(
                L,
                "Bias = sum(Forecast - Actual) / sum(Actual) "
                + (f"in {period_text(it.months, L)}." if it.months else "over the last 12 backtest months."),
                "Viés = soma(Forecast − Real) / soma(Real) "
                + (f"{period_prep(it.months, L, 'em')}." if it.months else "nos últimos 12 meses de backtest."),
            )
        ],
        metrics=[
            {
                "label": t(L, f"{_cap(dl)} flagged", f"{_cap(dl)} {agree('sinalizados', dim, L)}"),
                "value": int(flagged.sum()),
                "format": "number",
                "tone": "red" if over else "blue",
            }
        ],
        chart={
            "type": "bar",
            "horizontal": True,
            "format": "percent_signed",
            "title": t(L, f"Bias by {dim_label(dim, L)}", f"Viés por {dim_label(dim, L)}"),
            "x": names,
            "series": [{"name": t(L, "Bias", "Viés"), "data": sel["bias"].tolist()}],
        }
        if len(sel)
        else None,
        table={
            "columns": [dim_title(dim, L), t(L, "Bias", "Viés"), "WMAPE", "Volume"],
            "rows": [[n, b, w, v] for n, b, w, v in zip(names, sel["bias"], sel["wmape"], sel["volume"], strict=True)],
            "formats": ["text", "percent_signed", "percent", "units"],
        }
        if len(sel)
        else None,
        recommendations=[
            t(
                L,
                "Review recent level changes (delistings, lost distribution) for the over-forecasted "
                "accounts and recalibrate the base."
                if over
                else "Check unconstrained demand (stock-outs) and new distribution not captured by the model.",
                "Revise mudanças recentes de patamar (deslistagens, perda de distribuição) nas contas "
                "superestimadas e recalibre a base."
                if over
                else "Verifique demanda não atendida (rupturas) e nova distribuição não capturada pelo modelo.",
            )
        ],
        filters=it.filters,
        facts={
            "items": [
                {"name": n, "bias": b, "wmape": w} for n, b, w in zip(names, sel["bias"], sel["wmape"], strict=True)
            ],
            "threshold": 0.05,
        },
        query=q.describe(),
    )


def h_target(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = _lang(it)
    a = assess(ctx, it.filters, it.months or None, "revenue")
    if not a.get("available"):
        return _result(answer=a.get("message", ""), filters=it.filters)
    period = period_text(it.months or None, L)
    cls = class_label(a["classification"], L)
    answer = t(
        L,
        f"The target for {period} ({_scope(ctx, it)}) is {cls}: target {money(a['target'], L)} vs consensus "
        f"{money(a['consensus'], L)} (P10 {money(a['p10'], L)} - P90 {money(a['p90'], L)}). Probability of reaching "
        f"it: {pct(a['probability'], L, digits=0)}. It requires {pct(a['required_growth'], L, True)} vs last year, "
        f"while the forecast implies {pct(a['forecast_growth'], L, True)}.",
        f"A meta {period_prep(it.months, L, 'de')} ({_scope(ctx, it)}) é {cls}: meta de {money(a['target'], L)} vs consenso de "
        f"{money(a['consensus'], L)} (P10 {money(a['p10'], L)} – P90 {money(a['p90'], L)}). Probabilidade de "
        f"atingir: {pct(a['probability'], L, digits=0)}. Exige {pct(a['required_growth'], L, True)} vs ano anterior, "
        f"enquanto o forecast indica {pct(a['forecast_growth'], L, True)}.",
    )
    lever_txt = []
    for lv in a.get("levers", []):
        rc = lv.get("required_change")
        if rc is None or not lv.get("plausible"):
            continue
        if lv["lever"] == "Promotions":
            lever_txt.append(
                t(
                    L,
                    f"~{dec(rc, L, 1)} additional promoted months (uplift {pct(lv['elasticity'], L, digits=0)})",
                    f"~{dec(rc, L, 1)} meses adicionais de promoção (incremento de {pct(lv['elasticity'], L, digits=0)})",
                )
            )
        else:
            lever_txt.append(
                t(
                    L,
                    f"{lever(lv['lever'], L)} {pct(rc, L, True)} (elasticity {dec(lv['elasticity'], L)})",
                    f"{lever(lv['lever'], L)} {pct(rc, L, True)} (elasticidade {dec(lv['elasticity'], L)})",
                )
            )
    recs = [a["recommendation"]] if a.get("recommendation") else []
    if lever_txt:
        recs.append(
            t(
                L,
                "Plausible single levers that would close the gap: " + "; ".join(lever_txt) + ".",
                "Alavancas plausíveis que fechariam o gap sozinhas: " + "; ".join(lever_txt) + ".",
            )
        )
    elif a.get("levers"):
        recs.append(
            t(
                L,
                "No single lever closes the gap within plausible ranges - it needs a combination of actions "
                "or a target revision.",
                "Nenhuma alavanca isolada fecha o gap em faixas plausíveis – é preciso combinar ações ou revisar a meta.",
            )
        )
    return _result(
        answer=answer,
        insights=a.get("reasons", []),
        metrics=[
            {
                "label": t(L, "Classification", "Classificação"),
                "value": cls,
                "format": "text",
                "tone": a.get("display", {}).get("color"),
            },
            {"label": t(L, "Target", "Meta"), "value": a["target"], "format": "currency", "tone": "navy"},
            {
                "label": t(L, "Consensus (P50)", "Consenso (P50)"),
                "value": a["consensus"],
                "format": "currency",
                "tone": "blue",
            },
            {
                "label": t(L, "Probability", "Probabilidade"),
                "value": a["probability"],
                "format": "percent",
                "tone": "purple",
            },
            {"label": "P90", "value": a["p90"], "format": "currency", "tone": "teal"},
            {
                "label": t(L, "Gap vs consensus", "Gap vs consenso"),
                "value": a["calibration"]["gap_vs_consensus_pct"],
                "format": "percent_signed",
                "tone": "orange",
            },
        ],
        chart={
            "type": "bar",
            "format": "currency",
            "title": t(L, "Target vs forecast range", "Meta vs faixa do forecast"),
            "x": [t(L, "Budget", "Orçamento"), "P10", "P50", "P90", t(L, "Target", "Meta")],
            "series": [
                {"name": t(L, "Value", "Valor"), "data": [a["budget"], a["p10"], a["p50"], a["p90"], a["target"]]}
            ],
            "highlight": 4,
        },
        recommendations=recs,
        filters=it.filters,
        facts={
            k: a.get(k)
            for k in (
                "classification",
                "target",
                "budget",
                "consensus",
                "p10",
                "p90",
                "probability",
                "required_growth",
                "forecast_growth",
                "historical_growth",
                "last_year",
                "planned_events",
                "capacity_ratio",
            )
        }
        | {
            "gap_vs_consensus": a["calibration"]["gap_vs_consensus"],
            "gap_vs_consensus_pct": a["calibration"]["gap_vs_consensus_pct"],
            "required_incremental_vs_budget": a["calibration"]["required_incremental_vs_budget"],
            "levers": a.get("levers", []),
        },
        query=f"feasibility.assess(filtros={it.filters}, meses={it.months or 'horizonte'}, medida=receita)",
    )


def h_best_model(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = _lang(it)
    lb = leaderboard(ctx, it.filters)
    if not lb:
        return _result(
            answer=t(L, "No backtest results for this selection.", "Sem resultados de backtest para esta seleção."),
            filters=it.filters,
        )
    best = lb[0]
    s = ctx.series[ctx.series["series_id"].isin(filter_ids(ctx, it.filters))]
    champs = s["champion"].value_counts()
    runner = lb[1] if len(lb) > 1 else None
    bm = model_name(best["model"], L)
    answer = t(
        L,
        f"For {_scope(ctx, it)}, {bm} performs best in the rolling-origin backtest with WMAPE "
        f"{pct(best['wmape'], L)} (bias {pct(best['bias'], L, True)}) across {best['series_evaluated']} series"
        + (f"; runner-up is {model_name(runner['model'], L)} ({pct(runner['wmape'], L)})." if runner else ".")
        + f" The most frequent champion is {model_name(champs.index[0], L)} ({int(champs.iloc[0])} of {len(s)} series).",
        f"Para {_scope(ctx, it, 'art')}, o melhor modelo no backtest com origem móvel é {bm}, com WMAPE de "
        f"{pct(best['wmape'], L)} (viés {pct(best['bias'], L, True)}) em {best['series_evaluated']} séries"
        + (f"; o segundo é {model_name(runner['model'], L)} ({pct(runner['wmape'], L)})." if runner else ".")
        + f" O campeão mais frequente é {model_name(champs.index[0], L)} ({int(champs.iloc[0])} de {len(s)} séries).",
    )
    top = lb[:8]
    return _result(
        answer=answer,
        insights=[
            t(
                L,
                "Models compete only where routed (e.g. Croston/SBA/TSB for intermittent series), so "
                "pooled WMAPE compares different subsets of series.",
                "Os modelos competem apenas onde são roteados (ex.: Croston/SBA/TSB para séries intermitentes), "
                "então o WMAPE agregado compara subconjuntos diferentes de séries.",
            )
        ],
        metrics=[
            {"label": t(L, "Best model", "Melhor modelo"), "value": bm, "format": "text", "tone": "yellow"},
            {"label": "WMAPE", "value": best["wmape"], "format": "percent", "tone": "orange"},
            {
                "label": t(L, "Champion in", "Campeão em (séries)"),
                "value": int(champs.get(best["model"], 0)),
                "format": "number",
                "tone": "blue",
            },
        ],
        chart={
            "type": "bar",
            "format": "percent",
            "title": t(L, "Backtest WMAPE by model", "WMAPE do backtest por modelo"),
            "x": [model_name(r["model"], L) for r in top],
            "series": [{"name": "WMAPE", "data": [r["wmape"] for r in top]}],
        },
        table={
            "columns": [
                t(L, "Model", "Modelo"),
                "WMAPE",
                t(L, "Bias", "Viés"),
                "RMSE",
                t(L, "Series", "Séries"),
                t(L, "Champion", "Campeão"),
                t(L, "Rank", "Posição"),
            ],
            "rows": [
                [
                    model_name(r["model"], L),
                    r["wmape"],
                    r["bias"],
                    r["rmse"],
                    r["series_evaluated"],
                    r["champion_count"],
                    r["rank"],
                ]
                for r in top
            ],
            "formats": ["text", "percent", "percent_signed", "number", "number", "number", "number"],
        },
        recommendations=[
            t(
                L,
                f"Keep {bm} as the default for similar series and monitor the challenger.",
                f"Mantenha {bm} como padrão para séries similares e monitore o desafiante.",
            )
        ],
        filters=it.filters,
        facts={
            "leaderboard": [
                {
                    "model": r["model"],
                    "wmape": r["wmape"],
                    "bias": r["bias"],
                    "series": r["series_evaluated"],
                    "champion_count": r["champion_count"],
                }
                for r in top
            ],
            "most_frequent_champion": champs.index[0],
            "champion_series": int(champs.iloc[0]),
            "total_series": len(s),
        },
        query=f"leaderboard(filtros={it.filters}) sobre backtest_results",
    )


def h_what_if(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = _lang(it)
    lv = it.levers
    if not lv:
        return _result(
            answer=t(
                L,
                "Tell me which lever and how much to simulate - e.g. price, distribution, marketing, promotion or "
                "market growth.",
                "Diga qual alavanca e quanto simular – por exemplo preço, distribuição, marketing, promoção ou "
                "crescimento de mercado.",
            ),
            recommendations=[
                t(L, "What happens if price drops 5%?", "O que acontece se o preço cair 5%?"),
                t(L, "What if distribution increases 10% in the South?", "E se a distribuição aumentar 10% no Sul?"),
                t(L, "What if we run a promotion in December?", "E se fizermos uma promoção em dezembro?"),
                t(L, "What if marketing grows 20%?", "E se o investimento em marketing subir 20%?"),
            ],
            filters=it.filters,
        )
    peak = ctx.forecast.groupby("date")["p50"].sum().sort_values(ascending=False)
    default_months = [d.strftime("%Y-%m-01") for d in sorted(peak.index[:3])]
    params = ScenarioParams(
        price_change_pct=float(lv.get("price", 0) or 0),
        distribution_change_pct=float(lv.get("distribution", 0) or 0),
        marketing_change_pct=float(lv.get("marketing", 0) or 0),
        customer_growth_pct=float(lv.get("customer_growth", 0) or 0),
        market_growth_pct=float(lv.get("market_growth", 0) or 0),
        promo_months=(it.months or default_months) if lv.get("promotion") else [],
        merch_months=(it.months or default_months[:2]) if lv.get("merchandising") else [],
        scope=it.filters,
    )
    sim = simulate(ctx, params, it.filters or None)
    tt = sim["totals"]
    el = estimate_elasticities(ctx.version)
    cats = ctx.series[ctx.series["series_id"].isin(filter_ids(ctx, it.filters))]["category"].unique()
    used = {
        c: {
            k: for_category(el, c)[k]
            for k in ("price_elasticity", "distribution_elasticity", "marketing_elasticity", "promo_uplift")
        }
        for c in cats
    }
    lever_txt = ", ".join(
        f"{lever(k, L)} {pct(v, L, True)}" if isinstance(v, float) else lever(k, L) for k, v in lv.items()
    )
    answer = t(
        L,
        f"With {lever_txt} on {_scope(ctx, it)}, the 12-month forecast moves from {money(tt['base_revenue'], L)} to "
        f"{money(tt['revenue'], L)} ({pct(tt['vs_base_revenue'], L, True)}) in revenue and "
        f"{pct(tt['vs_base_units'], L, True)} in units ({units(tt['units'] - tt['base_units'], L)}). "
        f"The scenario lands {pct(tt['vs_budget_revenue'], L, True)} vs budget and "
        f"{pct(tt['vs_target_revenue'], L, True)} vs target.",
        f"Com {lever_txt} para {_scope(ctx, it, 'art')}, o forecast de 12 meses vai de {money(tt['base_revenue'], L)} "
        f"para {money(tt['revenue'], L)} ({pct(tt['vs_base_revenue'], L, True)}) em receita e "
        f"{pct(tt['vs_base_units'], L, True)} em volume ({units(tt['units'] - tt['base_units'], L)}). "
        f"O cenário fica {pct(tt['vs_budget_revenue'], L, True)} vs orçamento e "
        f"{pct(tt['vs_target_revenue'], L, True)} vs meta.",
    )
    insights = []
    for c, e in list(used.items())[:4]:
        insights.append(
            t(
                L,
                f"{c}: price elasticity {dec(e['price_elasticity'], L)}, distribution elasticity "
                f"{dec(e['distribution_elasticity'], L)}, promo uplift {pct(e['promo_uplift'], L, digits=0)}.",
                f"{c}: elasticidade-preço {dec(e['price_elasticity'], L)}, elasticidade-distribuição "
                f"{dec(e['distribution_elasticity'], L)}, incremento promocional {pct(e['promo_uplift'], L, digits=0)}.",
            )
        )
    if params.promo_months:
        insights.append(
            t(
                L,
                f"Promotions applied in: {', '.join(month_name(m, L) for m in params.promo_months)}.",
                f"Promoções aplicadas em: {', '.join(month_name(m, L) for m in params.promo_months)}.",
            )
        )
    m = sim["monthly"]
    return _result(
        answer=answer,
        insights=insights,
        metrics=[
            {
                "label": t(L, "Scenario revenue", "Receita do cenário"),
                "value": tt["revenue"],
                "format": "currency",
                "tone": "blue",
            },
            {"label": "vs Base", "value": tt["vs_base_revenue"], "format": "percent_signed", "tone": "teal"},
            {
                "label": t(L, "Scenario units", "Volume do cenário"),
                "value": tt["units"],
                "format": "units",
                "tone": "navy",
            },
            {
                "label": t(L, "vs Budget", "vs Orçamento"),
                "value": tt["vs_budget_revenue"],
                "format": "percent_signed",
                "tone": "green",
            },
            {
                "label": t(L, "vs Target", "vs Meta"),
                "value": tt["vs_target_revenue"],
                "format": "percent_signed",
                "tone": "orange",
            },
        ],
        chart={
            "type": "line",
            "format": "currency",
            "title": t(L, "Base vs scenario (revenue)", "Base vs cenário (receita)"),
            "x": [month_short(r["date"], L) for r in m],
            "series": [
                {"name": "Base", "data": [r["base_revenue"] for r in m]},
                {"name": t(L, "Scenario", "Cenário"), "data": [r["scenario_revenue"] for r in m]},
                {"name": t(L, "Target", "Meta"), "data": [r.get("target_revenue") for r in m], "dashed": True},
            ],
        },
        table={
            "columns": [t(L, "Lever", "Alavanca"), t(L, "Units impact", "Impacto em unidades")],
            "rows": [[lever(d["lever"], L).capitalize(), d["units"]] for d in sim["drivers"]],
            "formats": ["text", "units"],
        },
        recommendations=[
            t(
                L,
                "Save this as a custom scenario in the Scenarios page to compare it with Base, "
                "Conservative and Aggressive.",
                "Salve como cenário personalizado na página Cenários para comparar com Base, Conservador e Agressivo.",
            )
        ],
        filters=it.filters,
        facts={"params": params.as_dict(), "totals": tt, "drivers": sim["drivers"], "elasticities": used},
        query=f"scenario.simulate({ {k: v for k, v in params.as_dict().items() if v} })",
    )


def h_fva(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = _lang(it)
    r = fva_report(ctx, it.filters)
    s = r.get("summary", {})
    if not s.get("overrides"):
        return _result(
            answer=t(
                L,
                "There are no historical overrides to evaluate in this dataset.",
                "Não há ajustes comerciais históricos para avaliar nesta base.",
            ),
            filters=it.filters,
        )
    worst = [o for o in r["overrides"] if o["outcome"] == "Worsened"][:8]
    by_ev = sorted(r["by_event_type"], key=lambda x: x["fva_pp"] or 0)
    neg_ev = [e for e in by_ev if (e["fva_pp"] or 0) < 0]
    ex = r["examples"][0]
    group_key = "planner" if it.dimension == "planner" else "event_type"
    groups = r["by_planner"] if group_key == "planner" else r["by_event_type"]
    neg_txt = ", ".join(event_type(e["event_type"], L) for e in neg_ev[:3])
    answer = t(
        L,
        f"Of {s['overrides']} overrides in the last 12 months, {s['improved']} ({pct(s['value_added_pct'], L, digits=0)}) "
        f"improved accuracy and {s['worsened']} reduced it. On overridden cells WMAPE went from "
        f"{pct(s['wmape_statistical_overridden'], L)} (statistical) to {pct(s['wmape_consensus_overridden'], L)} "
        f"(consensus). Overrides that reduced accuracy were mostly: {neg_txt or 'none by type'}. Example: "
        f"{ex['customer']} {ex['sku']} - statistical {num(ex['statistical'], L)}, override {num(ex['consensus'], L)}, "
        f"actual {num(ex['actual'], L)}.",
        f"Dos {s['overrides']} ajustes comerciais dos últimos 12 meses, {s['improved']} "
        f"({pct(s['value_added_pct'], L, digits=0)}) melhoraram a acurácia e {s['worsened']} pioraram. Nas células "
        f"ajustadas, o WMAPE foi de {pct(s['wmape_statistical_overridden'], L)} (estatístico) para "
        f"{pct(s['wmape_consensus_overridden'], L)} (consenso). Os ajustes que mais pioraram o forecast foram de: "
        f"{neg_txt or 'nenhum tipo específico'}. Exemplo: {ex['customer']} {ex['sku']} – estatístico "
        f"{num(ex['statistical'], L)}, ajuste {num(ex['consensus'], L)}, real {num(ex['actual'], L)}.",
    )
    pos = [g for g in groups if (g["fva_pp"] or 0) > 0]
    gl = dim_label(group_key, L)
    return _result(
        answer=answer,
        insights=[
            t(
                L,
                f"Best {gl}: {group_value(group_key, pos[0][group_key], L)} ({pp(pos[0]['fva_pp'], L)} of WMAPE).",
                f"Melhor {gl}: {group_value(group_key, pos[0][group_key], L)} ({pp(pos[0]['fva_pp'], L)} de WMAPE).",
            )
        ]
        if pos
        else [],
        metrics=[
            {
                "label": t(L, "Overrides adding value", "Ajustes que agregam valor"),
                "value": s["value_added_pct"],
                "format": "percent",
                "tone": "green",
            },
            {
                "label": t(L, "FVA (WMAPE pts)", "FVA (p.p. de WMAPE)"),
                "value": s["fva_pp_overridden"],
                "format": "percent_signed",
                "tone": "purple",
            },
            {
                "label": t(L, "Overrides evaluated", "Ajustes avaliados"),
                "value": s["overrides"],
                "format": "number",
                "tone": "blue",
            },
        ],
        chart={
            "type": "bar",
            "horizontal": True,
            "format": "percent_signed",
            "title": t(L, f"FVA by {gl} (WMAPE points)", f"FVA por {gl} (pontos de WMAPE)"),
            "x": [group_value(group_key, g[group_key], L) for g in groups],
            "series": [{"name": "FVA", "data": [g["fva_pp"] for g in groups]}],
        },
        table={
            "columns": [
                t(L, "Month", "Mês"),
                t(L, "Customer", "Cliente"),
                "SKU",
                t(L, "Planner", "Planejador"),
                t(L, "Event", "Evento"),
                t(L, "Adj.", "Ajuste"),
                t(L, "Statistical", "Estatístico"),
                t(L, "Override", "Consenso"),
                t(L, "Actual", "Real"),
            ],
            "rows": [
                [
                    month_short(o["date"], L),
                    o["customer"],
                    o["sku"],
                    planner(o["planner"], L),
                    event_type(o["event_type"], L),
                    o["adjustment_pct"],
                    o["statistical"],
                    o["consensus"],
                    o["actual"],
                ]
                for o in worst
            ],
            "formats": ["text", "text", "text", "text", "text", "percent_signed", "units", "units", "units"],
        },
        recommendations=[
            t(
                L,
                "Require a documented driver (promotion, listing, contract) for every override and "
                "review FVA by planner monthly.",
                "Exija um motivo documentado (promoção, listagem, contrato) para cada ajuste comercial e revise o FVA "
                "por planejador mensalmente.",
            )
        ],
        filters=it.filters,
        facts={
            "summary": s,
            "stairstep": r["stairstep"],
            "by_event_type": r["by_event_type"],
            "by_planner": r["by_planner"],
            "example": ex,
        },
        query="fva_report(últimos 12 meses de backtest: naive → estatístico → consenso)",
    )


def h_budget_gap(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = _lang(it)
    dim = it.dimension if it.dimension in RANK_DIMS else "customer"
    q = SemanticQuery("gap_vs_budget", dim, it.filters, it.months, "revenue", "asc", 50)
    df = run_query(ctx, q)
    months = pd.DatetimeIndex([pd.Timestamp(m) for m in it.months]) if it.months else None
    if months is not None:
        months = months[months.isin(ctx.future_dates)]
        if len(months) == 0:
            months = None
    tot = horizon_totals(ctx, filter_ids(ctx, it.filters), "revenue", months)
    if "gap_vs_budget" not in df:
        return _result(
            answer=t(L, "There is no budget loaded for this dataset.", "Não há orçamento carregado nesta base."),
            filters=it.filters,
        )
    below = df[df["gap_vs_budget"] < 0].head(8)
    above = df[df["gap_vs_budget"] > 0].sort_values("gap_vs_budget", ascending=False).head(3)
    names = [_label(ctx, dim, m) for m in below["member"]]
    gap = tot["consensus"] - (tot.get("budget") or 0)
    gap_pct = gap / tot["budget"] if tot.get("budget") else None
    pmonths = [d.strftime("%Y-%m-01") for d in months] if months is not None else None
    period = period_text(pmonths, L)
    answer = t(
        L,
        f"For {period} ({_scope(ctx, it)}) the consensus is {money(tot['consensus'], L)} vs budget "
        f"{money(tot.get('budget'), L)} ({money(gap, L)}, {pct(gap_pct, L, True)}). Largest shortfalls: "
        + (
            "; ".join(f"{n} ({money(g, L)})" for n, g in zip(names[:4], below["gap_vs_budget"][:4], strict=False))
            or "none"
        )
        + ".",
        f"{_cap(period_prep(pmonths, L, 'para'))} ({_scope(ctx, it)}), o consenso é {money(tot['consensus'], L)} vs orçamento de "
        f"{money(tot.get('budget'), L)} ({money(gap, L)}, {pct(gap_pct, L, True)}). "
        + ("Estamos abaixo do orçamento. " if gap < 0 else "Estamos acima do orçamento. ")
        + "Maiores gaps: "
        + (
            "; ".join(f"{n} ({money(g, L)})" for n, g in zip(names[:4], below["gap_vs_budget"][:4], strict=False))
            or "nenhum"
        )
        + ".",
    )
    plot = pd.concat([below, above])
    return _result(
        answer=answer,
        insights=[
            t(
                L,
                f"Upside where demand runs ahead of budget: {', '.join(_label(ctx, dim, m) for m in above['member'])}.",
                f"Oportunidade onde a demanda supera o orçamento: {', '.join(_label(ctx, dim, m) for m in above['member'])}.",
            )
        ]
        if len(above)
        else [],
        metrics=[
            {
                "label": t(L, "Gap vs budget", "Gap vs orçamento"),
                "value": gap,
                "format": "currency",
                "tone": "red" if gap < 0 else "green",
            },
            {"label": t(L, "Consensus", "Consenso"), "value": tot["consensus"], "format": "currency", "tone": "blue"},
            {"label": t(L, "Budget", "Orçamento"), "value": tot.get("budget"), "format": "currency", "tone": "navy"},
        ],
        chart={
            "type": "bar",
            "horizontal": True,
            "format": "currency",
            "title": t(L, f"Gap vs budget by {dim_label(dim, L)}", f"Gap vs orçamento por {dim_label(dim, L)}"),
            "x": [_label(ctx, dim, m) for m in plot["member"]],
            "series": [{"name": "Gap", "data": plot["gap_vs_budget"].tolist()}],
        },
        table={
            "columns": [dim_title(dim, L), t(L, "Consensus", "Consenso"), t(L, "Budget", "Orçamento"), "Gap"],
            "rows": [[_label(ctx, dim, r.member), r.consensus, r.budget, r.gap_vs_budget] for r in plot.itertuples()],
            "formats": ["text", "currency", "currency", "currency"],
        },
        recommendations=[
            t(
                L,
                "Bring the largest shortfalls to the S&OP pre-meeting with a recovery plan or a budget revision.",
                "Leve os maiores gaps para a pré-reunião de S&OP com plano de recuperação ou revisão de orçamento.",
            )
        ],
        filters=it.filters,
        facts={
            "consensus": tot["consensus"],
            "budget": tot.get("budget"),
            "gap": gap,
            "gap_pct": gap_pct,
            "shortfalls": [{"name": n, "gap": g} for n, g in zip(names, below["gap_vs_budget"], strict=True)],
        },
        query=q.describe(),
    )


def h_drivers(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = _lang(it)
    months = pd.DatetimeIndex([pd.Timestamp(m) for m in it.months]) if it.months else ctx.future_dates
    months = months[months.isin(ctx.future_dates)]
    explicit = bool(it.months) and len(months) > 0
    if len(months) == 0:
        months = ctx.future_dates
    ids = filter_ids(ctx, it.filters)
    f = ctx.forecast[ctx.forecast["series_id"].isin(ids) & ctx.forecast["date"].isin(months)].merge(
        ctx.series[["series_id", "category", "customer"]], on="series_id"
    )
    f = f.assign(base=f["p50"] * f["price"], cons=f["consensus"] * f["price"])
    ly_months = months - pd.DateOffset(years=1)
    a = ctx.actuals[ctx.actuals["series_id"].isin(ids) & ctx.actuals["date"].isin(ly_months)].merge(
        ctx.series[["series_id", "category", "customer"]], on="series_id"
    )
    ly_cat = a.groupby("category")["revenue"].sum()
    base_cat = f.groupby("category")["base"].sum()
    delta_cat = base_cat.subtract(ly_cat, fill_value=0).sort_values()
    events = float(f["cons"].sum() - f["base"].sum())
    ly, cons = float(a["revenue"].sum()), float(f["cons"].sum())
    growth = cons / ly - 1 if ly else None
    cust_delta = (
        f.groupby("customer")["cons"].sum().subtract(a.groupby("customer")["revenue"].sum(), fill_value=0).sort_values()
    )
    pmonths = [d.strftime("%Y-%m-01") for d in months] if explicit else None
    period = period_text(pmonths, L)
    pos = delta_cat[delta_cat > 0].sort_values(ascending=False)
    neg = delta_cat[delta_cat < 0]
    seasonal_note = ""
    if len(months) == 1:
        hist = ctx.actuals[ctx.actuals["series_id"].isin(ids)].groupby("date")["revenue"].sum()
        idx = hist.groupby(hist.index.month).mean()
        si = float(idx.get(months[0].month, float("nan")) / idx.mean()) if len(idx) else None
        if si and si == si:
            seasonal_note = t(
                L,
                f"Seasonality index for {month_only(months[0], L)}: {dec(si, L)} "
                f"({'peak' if si > 1.05 else 'low' if si < 0.95 else 'average'} season).",
                f"Índice sazonal de {month_only(months[0], L)}: {dec(si, L)} "
                f"({'alta' if si > 1.05 else 'baixa' if si < 0.95 else 'média'} temporada).",
            )
    pos_txt = ", ".join(f"{c} {money(v, L)}" for c, v in pos.head(2).items()) or t(
        L, "no positive contributors", "sem contribuições positivas"
    )
    neg_txt = ", ".join(f"{c} {money(v, L)}" for c, v in neg.head(2).items())
    answer = t(
        L,
        f"Consensus for {period} is {money(cons, L)}, {pct(growth, L, True)} vs the same period last year "
        f"({money(ly, L)}). Statistical drivers by category: {pos_txt}"
        + (f"; offsets: {neg_txt}" if neg_txt else "")
        + (f". Commercial events add {money(events, L)}." if abs(events) >= 1 else ". There are no commercial events."),
        f"O consenso {period_prep(pmonths, L, 'para')} é {money(cons, L)}, {pct(growth, L, True)} vs o mesmo período do ano "
        f"anterior ({money(ly, L)}). Contribuição estatística por categoria: {pos_txt}"
        + (f"; compensações: {neg_txt}" if neg_txt else "")
        + (
            f". Os eventos comerciais adicionam {money(events, L)}."
            if abs(events) >= 1
            else ". Não há eventos comerciais no período."
        ),
    )
    steps = [(t(L, "Last year", "Ano anterior"), ly, "total")]
    steps += [(str(c), float(v), "delta") for c, v in delta_cat.items()]
    steps += [
        (t(L, "Commercial events", "Eventos comerciais"), events, "delta"),
        (t(L, "Consensus", "Consenso"), cons, "total"),
    ]
    insights = [seasonal_note] if seasonal_note else []
    if len(cust_delta):
        insights.append(
            t(
                L,
                f"Largest customer contribution: {cust_delta.index[-1]} ({money(cust_delta.iloc[-1], L)}); "
                f"largest drag: {cust_delta.index[0]} ({money(cust_delta.iloc[0], L)}).",
                f"Maior contribuição de cliente: {cust_delta.index[-1]} ({money(cust_delta.iloc[-1], L)}); "
                f"maior queda: {cust_delta.index[0]} ({money(cust_delta.iloc[0], L)}).",
            )
        )
    return _result(
        answer=answer,
        insights=insights,
        metrics=[
            {"label": t(L, "Consensus", "Consenso"), "value": cons, "format": "currency", "tone": "blue"},
            {"label": t(L, "Last year", "Ano anterior"), "value": ly, "format": "currency", "tone": "navy"},
            {"label": t(L, "Growth", "Crescimento"), "value": growth, "format": "percent_signed", "tone": "green"},
            {
                "label": t(L, "Commercial events", "Eventos comerciais"),
                "value": events,
                "format": "currency",
                "tone": "purple",
            },
        ],
        chart={
            "type": "waterfall",
            "format": "currency",
            "title": t(L, "Bridge: last year -> consensus", "Ponte: ano anterior → consenso"),
            "x": [s[0] for s in steps],
            "series": [{"name": t(L, "Value", "Valor"), "data": [s[1] for s in steps]}],
            "kinds": [s[2] for s in steps],
        },
        recommendations=[
            t(
                L,
                "Validate the main category drivers with Marketing and confirm the commercial "
                "events with Key Accounts.",
                "Valide com Marketing os principais fatores de crescimento por categoria e confirme os eventos "
                "comerciais com os Key Accounts (KAM).",
            )
        ],
        filters=it.filters,
        facts={
            "consensus": cons,
            "last_year": ly,
            "growth": growth,
            "events": events,
            "category_drivers": {c: float(v) for c, v in delta_cat.items()},
            "top_customer": {cust_delta.index[-1]: float(cust_delta.iloc[-1])} if len(cust_delta) else {},
            "bottom_customer": {cust_delta.index[0]: float(cust_delta.iloc[0])} if len(cust_delta) else {},
        },
        query=f"ponte(real do ano anterior → estatístico por categoria → eventos → consenso, meses={it.months or 'horizonte'})",
    )


def h_risks(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = _lang(it)
    alerts = _alerts_for(ctx, it.filters)
    top = alerts[:8]
    sev = {k: sum(1 for a in alerts if a["severity"] == k) for k in ("critical", "high", "medium", "low")}
    lst = "; ".join(f"{a['title']} – {_alert_entity(a)} ({a['magnitude']})" for a in top[:3])
    if not alerts:
        answer = t(
            L,
            f"There are no open alerts for {_scope(ctx, it)}.",
            f"Não há alertas abertos para {_scope(ctx, it, 'art')}.",
        )
    else:
        answer = t(
            L,
            f"{len(alerts)} alerts are open for {_scope(ctx, it)} ({sev['critical']} critical, {sev['high']} high). "
            f"Top items: {lst}.",
            f"Há {plural(len(alerts), 'alerta aberto', 'alertas abertos')} para {_scope(ctx, it, 'art')} "
            f"({plural(sev['critical'], 'crítico', 'críticos')}, {plural(sev['high'], 'alto', 'altos')}). "
            f"Principais: {lst}.",
        )
    return _result(
        answer=answer,
        insights=[a["explanation"] for a in top[:3]],
        metrics=[
            {"label": t(L, "Critical", "Críticos"), "value": sev["critical"], "format": "number", "tone": "red"},
            {"label": t(L, "High", "Altos"), "value": sev["high"], "format": "number", "tone": "orange"},
            {"label": t(L, "Medium", "Médios"), "value": sev["medium"], "format": "number", "tone": "yellow"},
        ],
        table={
            "columns": [
                t(L, "Alert", "Alerta"),
                t(L, "Severity", "Severidade"),
                t(L, "Entity", "Entidade"),
                "Magnitude",
                t(L, "Impact (R$)", "Impacto (R$)"),
            ],
            "rows": [
                [
                    a["title"],
                    severity(a["severity"], L).capitalize(),
                    _alert_entity(a),
                    a["magnitude"],
                    a["potential_impact"],
                ]
                for a in top
            ],
            "formats": ["text", "text", "text", "text", "currency"],
        }
        if top
        else None,
        recommendations=list(dict.fromkeys(a["recommendation"] for a in top[:4] if a.get("recommendation")))[:2],
        filters=it.filters,
        facts={
            "counts": sev,
            "top": [{k: a[k] for k in ("title", "entity", "magnitude", "potential_impact")} for a in top],
        },
        query="alerts.build_alerts(execução ativa)",
    )


def h_model_distribution(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = _lang(it)
    s = ctx.series[ctx.series["series_id"].isin(filter_ids(ctx, it.filters))]
    c = s["champion"].value_counts()
    if not len(c):
        return _result(answer=t(L, "No champion models for this selection.", "Sem modelos campeões para esta seleção."))
    others = ", ".join(f"{model_name(m, L)} ({int(n)})" for m, n in c.iloc[1:4].items())
    answer = t(
        L,
        f"{model_name(c.index[0], L)} is the champion in {int(c.iloc[0])} of {len(s)} series "
        f"({pct(c.iloc[0] / len(s), L)})" + (f", followed by {others}." if others else "."),
        f"{model_name(c.index[0], L)} é o campeão em {int(c.iloc[0])} de {len(s)} séries "
        f"({pct(c.iloc[0] / len(s), L)})" + (f", seguido por {others}." if others else "."),
    )
    return _result(
        answer=answer,
        chart={
            "type": "bar",
            "format": "number",
            "title": t(L, "Champion models", "Modelos campeões"),
            "x": [model_name(x, L) for x in c.index],
            "series": [{"name": t(L, "Series", "Séries"), "data": c.tolist()}],
        },
        metrics=[
            {
                "label": t(L, "Distinct champions", "Campeões distintos"),
                "value": len(c),
                "format": "number",
                "tone": "yellow",
            },
            {"label": t(L, "Series", "Séries"), "value": len(s), "format": "number", "tone": "blue"},
        ],
        filters=it.filters,
        facts={"champions": {k: int(v) for k, v in c.items()}, "total_series": len(s)},
        query="count(series) BY champion",
    )


def h_series_types(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = _lang(it)
    s = ctx.series[ctx.series["series_id"].isin(filter_ids(ctx, it.filters))]
    c = s["series_type"].value_counts()
    answer = t(
        L,
        f"{_scope(ctx, it)[:1].upper() + _scope(ctx, it)[1:]} has {len(s)} customer x SKU series: "
        + ", ".join(f"{series_type(k, L)} {int(v)}" for k, v in c.items())
        + ".",
        f"{_scope(ctx, it, 'art')[:1].upper() + _scope(ctx, it, 'art')[1:]} tem {len(s)} séries cliente × SKU: "
        + ", ".join(f"{series_type(k, L)} {int(v)}" for k, v in c.items())
        + ".",
    )
    return _result(
        answer=answer,
        chart={
            "type": "bar",
            "format": "number",
            "title": t(L, "Series by demand pattern", "Séries por padrão de demanda"),
            "x": [series_type(x, L) for x in c.index],
            "series": [{"name": t(L, "Series", "Séries"), "data": c.tolist()}],
        },
        metrics=[
            {"label": t(L, "Series", "Séries"), "value": len(s), "format": "number", "tone": "blue"},
            {
                "label": t(L, "Demand patterns", "Padrões de demanda"),
                "value": len(c),
                "format": "number",
                "tone": "purple",
            },
        ],
        insights=[
            t(
                L,
                "Each pattern is routed to its own candidate models (e.g. Croston/SBA/TSB for intermittent).",
                "Cada padrão é roteado para seus modelos candidatos (ex.: Croston/SBA/TSB para intermitentes).",
            )
        ],
        filters=it.filters,
        facts={"types": {k: int(v) for k, v in c.items()}, "total_series": len(s)},
        query="count(series) BY series_type",
    )


HANDLERS = {
    "summary": h_summary,
    "forecast_value": h_forecast_value,
    "metric_lookup": h_metric_lookup,
    "entity_overview": h_entity_overview,
    "worst_accuracy": h_accuracy,
    "bias_ranking": h_bias,
    "target_feasibility": h_target,
    "best_model": h_best_model,
    "what_if": h_what_if,
    "fva_overrides": h_fva,
    "budget_gap": h_budget_gap,
    "forecast_drivers": h_drivers,
    "risks": h_risks,
    "model_distribution": h_model_distribution,
    "series_types": h_series_types,
}
