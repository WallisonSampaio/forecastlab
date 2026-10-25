"""Intent handlers: compute every number deterministically and draft the answer.

Each handler returns the structured AI response (answer, insights, metrics,
chart, table, recommendations, filters) plus ``facts`` - the only numbers
the LLM is allowed to use when it rewrites the explanation.
"""

from __future__ import annotations

from typing import Any

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
from .nlg import class_label, money, month_name, pct, t, units

DIM_LABEL = {
    "en": {
        "sku": "SKUs",
        "customer": "customers",
        "region": "regions",
        "channel": "channels",
        "category": "categories",
        "brand": "brands",
        "planner": "planners",
        "event_type": "event types",
    },
    "pt": {
        "sku": "SKUs",
        "customer": "clientes",
        "region": "regiões",
        "channel": "canais",
        "category": "categorias",
        "brand": "marcas",
        "planner": "planejadores",
        "event_type": "tipos de evento",
    },
}


LEVER_PT = {
    "distribution": "distribuição",
    "price": "preço",
    "marketing": "marketing",
    "promotion": "promoção",
    "merchandising": "merchandising",
    "customer_growth": "crescimento de clientes",
    "market_growth": "crescimento de mercado",
}


def _scope(intent: Intent) -> str:
    if not intent.filters:
        return t(intent.language, "the total portfolio", "o portfólio total")
    return ", ".join(str(v) for v in intent.filters.values())


def _label(ctx: PlanningContext, dim: str, member: str) -> str:
    if dim == "sku":
        p = ctx.series.loc[ctx.series["sku"] == member, "product"]
        return f"{member} {p.iloc[0]}" if len(p) else member
    return str(member)


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


# --------------------------------------------------------------------------------------- handlers
def h_summary(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = it.language
    ids = filter_ids(ctx, it.filters)
    tot = horizon_totals(ctx, ids, "revenue")
    m = backtest_metrics(ctx, ids)
    growth = tot["consensus"] / tot["actual_ltm"] - 1 if tot["actual_ltm"] else None
    gb = tot["consensus"] / tot["budget"] - 1 if tot.get("budget") else None
    gt = tot["consensus"] / tot["target"] - 1 if tot.get("target") else None
    tl = timeline(ctx, it.filters, "revenue", 24)
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    top_type = s["series_type"].value_counts()
    answer = t(
        L,
        f"For {_scope(it)}, the consensus forecast for the next 12 months is {money(tot['consensus'])} "
        f"({pct(growth, signed=True)} vs the last 12 months). Backtest forecast accuracy is {pct(m['accuracy'])} "
        f"(WMAPE {pct(m['wmape'])}, bias {pct(m['bias'], signed=True)}). The consensus is {pct(gb, signed=True)} vs "
        f"budget and {pct(gt, signed=True)} vs target.",
        f"Para {_scope(it)}, o consensus dos próximos 12 meses é {money(tot['consensus'], 'pt')} "
        f"({pct(growth, 'pt', True)} vs últimos 12 meses). A acurácia no backtest é {pct(m['accuracy'], 'pt')} "
        f"(WMAPE {pct(m['wmape'], 'pt')}, viés {pct(m['bias'], 'pt', True)}). O consensus está "
        f"{pct(gb, 'pt', True)} vs orçamento e {pct(gt, 'pt', True)} vs meta.",
    )
    insights = [
        t(
            L,
            f"Statistical base {money(tot['base'])} + commercial events {money(tot['incremental'])}.",
            f"Base estatística {money(tot['base'], 'pt')} + eventos comerciais {money(tot['incremental'], 'pt')}.",
        ),
        t(
            L,
            f"Most common demand pattern: {top_type.index[0]} ({int(top_type.iloc[0])} series).",
            f"Padrão de demanda mais comum: {top_type.index[0]} ({int(top_type.iloc[0])} séries).",
        )
        if len(top_type)
        else "",
        t(
            L,
            f"P10-P90 range for the year: {money(tot['p10'])} - {money(tot['p90'])}.",
            f"Faixa P10-P90 do ano: {money(tot['p10'], 'pt')} - {money(tot['p90'], 'pt')}.",
        ),
    ]
    return _result(
        answer=answer,
        insights=[i for i in insights if i],
        metrics=[
            {"label": t(L, "Consensus 12M", "Consensus 12M"), "value": tot["consensus"], "format": "currency"},
            {"label": t(L, "Forecast Accuracy", "Acurácia"), "value": m["accuracy"], "format": "percent"},
            {"label": "WMAPE", "value": m["wmape"], "format": "percent"},
            {"label": t(L, "Bias", "Viés"), "value": m["bias"], "format": "percent_signed"},
            {"label": t(L, "vs Budget", "vs Orçamento"), "value": gb, "format": "percent_signed"},
            {"label": t(L, "vs Target", "vs Meta"), "value": gt, "format": "percent_signed"},
        ],
        chart={
            "type": "line",
            "title": t(L, "Revenue: actual, consensus, budget", "Receita: real, consensus, orçamento"),
            "format": "currency",
            "x": [d.strftime("%Y-%m") for d in tl["date"]],
            "series": [
                {"name": t(L, "Actual", "Real"), "data": tl["actual"].tolist()},
                {"name": "Consensus", "data": tl.get("consensus", pd.Series(dtype=float)).tolist()},
                {
                    "name": t(L, "Budget", "Orçamento"),
                    "data": tl.get("budget", pd.Series(dtype=float)).tolist(),
                    "dashed": True,
                },
            ],
        },
        recommendations=[assess(ctx, it.filters, None, "revenue").get("recommendation", "")],
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


def h_accuracy(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = it.language
    dim = it.dimension if it.dimension in ("sku", "customer", "region", "channel", "category", "brand") else "sku"
    worst = it.direction != "best"
    q = SemanticQuery("wmape", dim, it.filters, it.months, "units", "desc" if worst else "asc", 25)
    df = run_query(ctx, q)
    total_vol = df["volume"].sum()
    df = df[df["volume"] >= 0.002 * max(total_vol, 1)].head(8)
    overall = backtest_metrics(ctx, filter_ids(ctx, it.filters))
    names = [_label(ctx, dim, m) for m in df["member"]]
    lst = "; ".join(f"{n} ({pct(w, L)})" for n, w in zip(names[:3], df["wmape"][:3], strict=False))
    dl = DIM_LABEL[L].get(dim, dim)
    answer = t(
        L,
        f"The {dl} with the {'worst' if worst else 'best'} forecast accuracy are: {lst}. "
        f"Overall WMAPE for {_scope(it)} is {pct(overall['wmape'])} (accuracy {pct(overall['accuracy'])}).",
        f"Os {dl} com {'pior' if worst else 'melhor'} acurácia são: {lst}. "
        f"O WMAPE geral para {_scope(it)} é {pct(overall['wmape'], 'pt')} (acurácia {pct(overall['accuracy'], 'pt')}).",
    )
    insights = []
    if dim == "sku" and len(df):
        types = ctx.series[ctx.series["sku"].isin(df["member"])]["series_type"].value_counts()
        insights.append(
            t(
                L,
                f"Dominant demand patterns among them: {', '.join(types.index[:3])}.",
                f"Padrões de demanda predominantes: {', '.join(types.index[:3])}.",
            )
        )
    share = df["volume"].sum() / total_vol if total_vol else None
    if share is not None:
        insights.append(
            t(
                L,
                f"They represent {pct(share)} of the evaluated volume.",
                f"Eles representam {pct(share, 'pt')} do volume avaliado.",
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
            {"label": t(L, "Overall WMAPE", "WMAPE geral"), "value": overall["wmape"], "format": "percent"},
            {"label": t(L, "Overall accuracy", "Acurácia geral"), "value": overall["accuracy"], "format": "percent"},
        ],
        chart={
            "type": "bar",
            "horizontal": True,
            "format": "percent",
            "title": t(L, f"WMAPE by {dim}", f"WMAPE por {dim}"),
            "x": names,
            "series": [{"name": "WMAPE", "data": df["wmape"].tolist()}],
        },
        table={
            "columns": [dim, "WMAPE", "Accuracy", "Bias", "Volume"],
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
    L = it.language
    dim = it.dimension if it.dimension in ("sku", "customer", "region", "channel", "category", "brand") else "customer"
    over = it.direction != "under"
    q = SemanticQuery("bias", dim, it.filters, it.months, "units", "desc" if over else "asc", 50)
    df = run_query(ctx, q)
    sel = df[df["bias"] > 0.05] if over else df[df["bias"] < -0.05]
    sel = sel.head(10)
    names = [_label(ctx, dim, m) for m in sel["member"]]
    dl = DIM_LABEL[L].get(dim, dim)
    if sel.empty:
        sel = df.head(5)
        names = [_label(ctx, dim, m) for m in sel["member"]]
        lst = "; ".join(f"{n} ({pct(b, L, True)})" for n, b in zip(names[:3], sel["bias"][:3], strict=False))
        answer = t(
            L,
            f"No {dl} exceed the ±5% bias threshold for {'over' if over else 'under'}-forecast. "
            f"The most {'over' if over else 'under'}-forecasted are: {lst}.",
            f"Nenhum(a) {dl} ultrapassa o limite de ±5% de {'super' if over else 'sub'}estimação. "
            f"Os mais {'super' if over else 'sub'}estimados são: {lst}.",
        )
    else:
        lst = "; ".join(f"{n} ({pct(b, L, True)})" for n, b in zip(names[:4], sel["bias"][:4], strict=False))
        answer = t(
            L,
            f"{len(sel)} {dl} are {'over' if over else 'under'}-forecasted (bias {'>' if over else '<'} "
            f"{'+' if over else '-'}5% in the backtest): {lst}.",
            f"{len(sel)} {dl} estão {'super' if over else 'sub'}estimados (viés {'>' if over else '<'} "
            f"{'+' if over else '-'}5% no backtest): {lst}.",
        )
    return _result(
        answer=answer,
        insights=[
            t(
                L,
                "Bias = sum(Forecast - Actual) / sum(Actual) over the last 12 backtest months.",
                "Viés = soma(Forecast - Real) / soma(Real) nos últimos 12 meses de backtest.",
            )
        ],
        metrics=[
            {"label": t(L, f"{dl.title()} flagged", f"{dl.title()} sinalizados"), "value": len(sel), "format": "number"}
        ],
        chart={
            "type": "bar",
            "horizontal": True,
            "format": "percent_signed",
            "title": t(L, f"Bias by {dim}", f"Viés por {dim}"),
            "x": names,
            "series": [{"name": "Bias", "data": sel["bias"].tolist()}],
        }
        if len(sel)
        else None,
        table={
            "columns": [dim, "Bias", "WMAPE", "Volume"],
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
    L = it.language
    a = assess(ctx, it.filters, it.months or None, "revenue")
    if not a.get("available"):
        return _result(answer=a.get("message", ""), filters=it.filters)
    period = (
        ", ".join(month_name(m, L) for m in it.months)
        if it.months
        else t(L, "the next 12 months", "os próximos 12 meses")
    )
    cls = class_label(a["classification"], L)
    answer = t(
        L,
        f"The target for {period} ({_scope(it)}) is {cls}: target {money(a['target'])} vs consensus "
        f"{money(a['consensus'])} (P10 {money(a['p10'])} - P90 {money(a['p90'])}). Probability of reaching it: "
        f"{pct(a['probability'], digits=0)}. It requires {pct(a['required_growth'], signed=True)} vs last year, while "
        f"the forecast implies {pct(a['forecast_growth'], signed=True)}.",
        f"A meta de {period} ({_scope(it)}) é {cls}: meta {money(a['target'], 'pt')} vs consensus "
        f"{money(a['consensus'], 'pt')} (P10 {money(a['p10'], 'pt')} - P90 {money(a['p90'], 'pt')}). Probabilidade "
        f"de atingir: {pct(a['probability'], 'pt', digits=0)}. Exige {pct(a['required_growth'], 'pt', True)} vs ano "
        f"anterior, enquanto o forecast indica {pct(a['forecast_growth'], 'pt', True)}.",
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
                    f"~{rc:.1f} additional promoted months (uplift {pct(lv['elasticity'], digits=0)})",
                    f"~{rc:.1f} meses adicionais de promoção (uplift {pct(lv['elasticity'], 'pt', digits=0)})",
                )
            )
        else:
            lever_txt.append(
                t(
                    L,
                    f"{lv['lever']} {pct(rc, signed=True)} (elasticity {lv['elasticity']:.2f})",
                    f"{lv['lever']} {pct(rc, 'pt', True)} (elasticidade {lv['elasticity']:.2f})",
                )
            )
    recs = [a["recommendation"]]
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
                "Nenhuma alavanca isolada fecha o gap em faixas plausíveis - é preciso combinar ações ou revisar a meta.",
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
                "tone": a["display"]["color"],
            },
            {"label": t(L, "Target", "Meta"), "value": a["target"], "format": "currency"},
            {"label": "Consensus (P50)", "value": a["consensus"], "format": "currency"},
            {"label": t(L, "Probability", "Probabilidade"), "value": a["probability"], "format": "percent"},
            {"label": "P90", "value": a["p90"], "format": "currency"},
            {
                "label": t(L, "Gap vs consensus", "Gap vs consensus"),
                "value": a["calibration"]["gap_vs_consensus_pct"],
                "format": "percent_signed",
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
        query=f"feasibility.assess(filters={it.filters}, months={it.months or 'horizon'}, measure=revenue)",
    )


def h_best_model(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = it.language
    lb = leaderboard(ctx, it.filters)
    if not lb:
        return _result(
            answer=t(L, "No backtest results for this selection.", "Sem resultados de backtest para esta seleção.")
        )
    best = lb[0]
    s = ctx.series[ctx.series["series_id"].isin(filter_ids(ctx, it.filters))]
    champs = s["champion"].value_counts()
    runner = lb[1] if len(lb) > 1 else None
    answer = t(
        L,
        f"For {_scope(it)}, {best['model']} performs best in the rolling-origin backtest with WMAPE "
        f"{pct(best['wmape'])} (bias {pct(best['bias'], signed=True)}) across {best['series_evaluated']} series"
        + (f"; runner-up is {runner['model']} ({pct(runner['wmape'])})." if runner else ".")
        + f" The most frequent champion is {champs.index[0]} ({int(champs.iloc[0])} of {len(s)} series).",
        f"Para {_scope(it)}, o melhor modelo no backtest rolling-origin é {best['model']} com WMAPE "
        f"{pct(best['wmape'], 'pt')} (viés {pct(best['bias'], 'pt', True)}) em {best['series_evaluated']} séries"
        + (f"; o segundo é {runner['model']} ({pct(runner['wmape'], 'pt')})." if runner else ".")
        + f" O campeão mais frequente é {champs.index[0]} ({int(champs.iloc[0])} de {len(s)} séries).",
    )
    top = lb[:8]
    return _result(
        answer=answer,
        insights=[
            t(
                L,
                "Models compete only where routed (e.g. Croston/SBA/TSB for intermittent series), so "
                "pooled WMAPE compares different subsets of series.",
                "Os modelos competem apenas onde roteados (ex.: Croston/SBA/TSB para séries intermitentes), "
                "então o WMAPE agregado compara subconjuntos diferentes.",
            )
        ],
        metrics=[
            {"label": t(L, "Best model", "Melhor modelo"), "value": best["model"], "format": "text"},
            {"label": "WMAPE", "value": best["wmape"], "format": "percent"},
            {
                "label": t(L, "Champion in", "Campeão em"),
                "value": int(champs.get(best["model"], 0)),
                "format": "number",
            },
        ],
        chart={
            "type": "bar",
            "format": "percent",
            "title": t(L, "Backtest WMAPE by model", "WMAPE do backtest por modelo"),
            "x": [r["model"] for r in top],
            "series": [{"name": "WMAPE", "data": [r["wmape"] for r in top]}],
        },
        table={
            "columns": ["Model", "WMAPE", "Bias", "RMSE", "Series", "Champion", "Rank"],
            "rows": [
                [r["model"], r["wmape"], r["bias"], r["rmse"], r["series_evaluated"], r["champion_count"], r["rank"]]
                for r in top
            ],
            "formats": ["text", "percent", "percent_signed", "number", "number", "number", "number"],
        },
        recommendations=[
            t(
                L,
                f"Keep {best['model']} as the default for similar series and monitor the challenger.",
                f"Mantenha {best['model']} como padrão para séries similares e monitore o challenger.",
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
        query=f"leaderboard(filters={it.filters}) over backtest_results",
    )


def h_what_if(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = it.language
    lv = it.levers
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
    names = LEVER_PT if L == "pt" else {k: k.replace("_", " ") for k in LEVER_PT}
    lever_txt = ", ".join(
        f"{names.get(k, k)} {pct(v, L, True)}" if isinstance(v, float) else names.get(k, k) for k, v in lv.items()
    )
    answer = t(
        L,
        f"With {lever_txt} on {_scope(it)}, the 12-month forecast moves from {money(tt['base_revenue'])} to "
        f"{money(tt['revenue'])} ({pct(tt['vs_base_revenue'], signed=True)}) in revenue and "
        f"{pct(tt['vs_base_units'], signed=True)} in units ({units(tt['units'] - tt['base_units'])}). "
        f"The scenario lands {pct(tt['vs_budget_revenue'], signed=True)} vs budget and "
        f"{pct(tt['vs_target_revenue'], signed=True)} vs target.",
        f"Com {lever_txt} para {_scope(it)}, o forecast de 12 meses vai de {money(tt['base_revenue'], 'pt')} para "
        f"{money(tt['revenue'], 'pt')} ({pct(tt['vs_base_revenue'], 'pt', True)}) em receita e "
        f"{pct(tt['vs_base_units'], 'pt', True)} em volume ({units(tt['units'] - tt['base_units'], 'pt')}). "
        f"O cenário fica {pct(tt['vs_budget_revenue'], 'pt', True)} vs orçamento e "
        f"{pct(tt['vs_target_revenue'], 'pt', True)} vs meta.",
    )
    insights = []
    for c, e in list(used.items())[:4]:
        insights.append(
            t(
                L,
                f"{c}: price elasticity {e['price_elasticity']:.2f}, distribution elasticity "
                f"{e['distribution_elasticity']:.2f}, promo uplift {pct(e['promo_uplift'], digits=0)}.",
                f"{c}: elasticidade-preço {e['price_elasticity']:.2f}, elasticidade-distribuição "
                f"{e['distribution_elasticity']:.2f}, uplift promocional {pct(e['promo_uplift'], 'pt', digits=0)}.",
            )
        )
    if params.promo_months:
        insights.append(
            t(
                L,
                f"Promotions applied in: {', '.join(month_name(m) for m in params.promo_months)}.",
                f"Promoções aplicadas em: {', '.join(month_name(m, 'pt') for m in params.promo_months)}.",
            )
        )
    m = sim["monthly"]
    return _result(
        answer=answer,
        insights=insights,
        metrics=[
            {"label": t(L, "Scenario revenue", "Receita do cenário"), "value": tt["revenue"], "format": "currency"},
            {"label": "vs Base", "value": tt["vs_base_revenue"], "format": "percent_signed"},
            {"label": t(L, "Scenario units", "Volume do cenário"), "value": tt["units"], "format": "units"},
            {"label": t(L, "vs Budget", "vs Orçamento"), "value": tt["vs_budget_revenue"], "format": "percent_signed"},
            {"label": t(L, "vs Target", "vs Meta"), "value": tt["vs_target_revenue"], "format": "percent_signed"},
        ],
        chart={
            "type": "line",
            "format": "currency",
            "title": t(L, "Base vs scenario (revenue)", "Base vs cenário (receita)"),
            "x": [r["date"][:7] for r in m],
            "series": [
                {"name": "Base", "data": [r["base_revenue"] for r in m]},
                {"name": t(L, "Scenario", "Cenário"), "data": [r["scenario_revenue"] for r in m]},
                {"name": t(L, "Target", "Meta"), "data": [r.get("target_revenue") for r in m], "dashed": True},
            ],
        },
        table={
            "columns": ["Lever", "Units impact"],
            "rows": [[d["lever"], d["units"]] for d in sim["drivers"]],
            "formats": ["text", "units"],
        },
        recommendations=[
            t(
                L,
                "Save this as a custom scenario in the Scenarios page to compare it with Base, "
                "Conservative and Aggressive.",
                "Salve como cenário customizado na página de Cenários para comparar com Base, Conservador e Agressivo.",
            )
        ],
        filters=it.filters,
        facts={"params": params.as_dict(), "totals": tt, "drivers": sim["drivers"], "elasticities": used},
        query=f"scenario.simulate({ {k: v for k, v in params.as_dict().items() if v} })",
    )


def h_fva(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = it.language
    r = fva_report(ctx, it.filters)
    s = r.get("summary", {})
    if not s.get("overrides"):
        return _result(
            answer=t(
                L,
                "There are no historical overrides to evaluate in this dataset.",
                "Não há ajustes históricos para avaliar neste dataset.",
            ),
            filters=it.filters,
        )
    worst = [o for o in r["overrides"] if o["outcome"] == "Worsened"][:8]
    by_ev = sorted(r["by_event_type"], key=lambda x: x["fva_pp"] or 0)
    neg_ev = [e for e in by_ev if (e["fva_pp"] or 0) < 0]
    ex = r["examples"][0]
    group_key = "planner" if it.dimension == "planner" else "event_type"
    groups = r["by_planner"] if group_key == "planner" else r["by_event_type"]
    answer = t(
        L,
        f"Of {s['overrides']} overrides in the last 12 months, {s['improved']} ({pct(s['value_added_pct'], digits=0)}) "
        f"improved accuracy and {s['worsened']} reduced it. On overridden cells WMAPE went from "
        f"{pct(s['wmape_statistical_overridden'])} (statistical) to {pct(s['wmape_consensus_overridden'])} "
        f"(consensus). Overrides that reduced accuracy were mostly: "
        f"{', '.join(e['event_type'] for e in neg_ev[:3]) or 'none by type'}. Example: {ex['customer']} {ex['sku']} - "
        f"statistical {ex['statistical']:,.0f}, override {ex['consensus']:,.0f}, actual {ex['actual']:,.0f}.",
        f"Dos {s['overrides']} ajustes dos últimos 12 meses, {s['improved']} ({pct(s['value_added_pct'], 'pt', digits=0)}) "
        f"melhoraram a acurácia e {s['worsened']} pioraram. Nas células ajustadas o WMAPE foi de "
        f"{pct(s['wmape_statistical_overridden'], 'pt')} (estatístico) para {pct(s['wmape_consensus_overridden'], 'pt')} "
        f"(consensus). Os ajustes que pioraram foram principalmente: "
        f"{', '.join(e['event_type'] for e in neg_ev[:3]) or 'nenhum tipo'}. Exemplo: {ex['customer']} {ex['sku']} - "
        f"estatístico {ex['statistical']:,.0f}, ajuste {ex['consensus']:,.0f}, real {ex['actual']:,.0f}.",
    )
    pos = [g for g in groups if (g["fva_pp"] or 0) > 0]
    return _result(
        answer=answer,
        insights=[
            t(
                L,
                f"Best {group_key.replace('_', ' ')}: {pos[0][group_key]} ({pct(pos[0]['fva_pp'], signed=True)} "
                f"WMAPE points).",
                f"Melhor {group_key.replace('_', ' ')}: {pos[0][group_key]} "
                f"({pct(pos[0]['fva_pp'], 'pt', True)} pontos de WMAPE).",
            )
        ]
        if pos
        else [],
        metrics=[
            {
                "label": t(L, "Overrides adding value", "Ajustes que agregam"),
                "value": s["value_added_pct"],
                "format": "percent",
            },
            {
                "label": t(L, "FVA (WMAPE pts)", "FVA (pts WMAPE)"),
                "value": s["fva_pp_overridden"],
                "format": "percent_signed",
            },
            {"label": t(L, "Overrides evaluated", "Ajustes avaliados"), "value": s["overrides"], "format": "number"},
        ],
        chart={
            "type": "bar",
            "horizontal": True,
            "format": "percent_signed",
            "title": t(
                L,
                f"FVA by {group_key.replace('_', ' ')} (WMAPE points)",
                f"FVA por {group_key.replace('_', ' ')} (pontos de WMAPE)",
            ),
            "x": [g[group_key] for g in groups],
            "series": [{"name": "FVA", "data": [g["fva_pp"] for g in groups]}],
        },
        table={
            "columns": ["Month", "Customer", "SKU", "Planner", "Event", "Adj.", "Statistical", "Override", "Actual"],
            "rows": [
                [
                    o["date"][:7],
                    o["customer"],
                    o["sku"],
                    o["planner"],
                    o["event_type"],
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
                "Exija um driver documentado (promoção, listagem, "
                "contrato) para cada ajuste e revise o FVA por "
                "planejador mensalmente.",
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
        query="fva_report(last 12 backtest months: naive -> statistical -> consensus)",
    )


def h_budget_gap(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = it.language
    dim = it.dimension if it.dimension in ("sku", "customer", "region", "channel", "category", "brand") else "customer"
    q = SemanticQuery("gap_vs_budget", dim, it.filters, it.months, "revenue", "asc", 50)
    df = run_query(ctx, q)
    tot = horizon_totals(ctx, filter_ids(ctx, it.filters), "revenue")
    below = df[df["gap_vs_budget"] < 0].head(8)
    above = df[df["gap_vs_budget"] > 0].sort_values("gap_vs_budget", ascending=False).head(3)
    names = [_label(ctx, dim, m) for m in below["member"]]
    gap = tot["consensus"] - (tot.get("budget") or 0)
    answer = t(
        L,
        f"The consensus is {money(tot['consensus'])} vs budget {money(tot.get('budget'))} "
        f"({money(gap)}, {pct(gap / tot['budget'] if tot.get('budget') else None, signed=True)}). Largest shortfalls: "
        + (
            "; ".join(f"{n} ({money(g)})" for n, g in zip(names[:4], below["gap_vs_budget"][:4], strict=False))
            or "none"
        )
        + ".",
        f"O consensus é {money(tot['consensus'], 'pt')} vs orçamento {money(tot.get('budget'), 'pt')} "
        f"({money(gap, 'pt')}, {pct(gap / tot['budget'] if tot.get('budget') else None, 'pt', True)}). Maiores gaps: "
        + (
            "; ".join(f"{n} ({money(g, 'pt')})" for n, g in zip(names[:4], below["gap_vs_budget"][:4], strict=False))
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
                f"Upside onde a demanda supera o orçamento: {', '.join(_label(ctx, dim, m) for m in above['member'])}.",
            )
        ]
        if len(above)
        else [],
        metrics=[
            {"label": t(L, "Gap vs budget", "Gap vs orçamento"), "value": gap, "format": "currency"},
            {"label": t(L, "Consensus 12M", "Consensus 12M"), "value": tot["consensus"], "format": "currency"},
            {"label": t(L, "Budget 12M", "Orçamento 12M"), "value": tot.get("budget"), "format": "currency"},
        ],
        chart={
            "type": "bar",
            "horizontal": True,
            "format": "currency",
            "title": t(L, f"Gap vs budget by {dim}", f"Gap vs orçamento por {dim}"),
            "x": [_label(ctx, dim, m) for m in plot["member"]],
            "series": [{"name": "Gap", "data": plot["gap_vs_budget"].tolist()}],
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
            "shortfalls": [{"name": n, "gap": g} for n, g in zip(names, below["gap_vs_budget"], strict=True)],
        },
        query=q.describe(),
    )


def h_drivers(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = it.language
    months = pd.DatetimeIndex([pd.Timestamp(m) for m in it.months]) if it.months else ctx.future_dates
    months = months[months.isin(ctx.future_dates)]
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
    period = (
        ", ".join(month_name(m.strftime("%Y-%m-%d"), L) for m in months)
        if it.months
        else t(L, "the next 12 months", "os próximos 12 meses")
    )
    pos = delta_cat[delta_cat > 0].sort_values(ascending=False)
    neg = delta_cat[delta_cat < 0]
    seasonal_note = ""
    if len(months) == 1:
        hist = ctx.actuals[ctx.actuals["series_id"].isin(ids)].groupby("date")["revenue"].sum()
        idx = hist.groupby(hist.index.month).mean()
        si = float(idx.get(months[0].month, float("nan")) / idx.mean()) if len(idx) else None
        if si:
            seasonal_note = t(
                L,
                f"Seasonality index for {months[0].strftime('%B')}: {si:.2f} "
                f"({'peak' if si > 1.05 else 'low' if si < 0.95 else 'average'} season).",
                f"Índice sazonal de {month_name(months[0].strftime('%Y-%m-%d'), 'pt').split('/')[0]}: "
                f"{si:.2f} ({'alta' if si > 1.05 else 'baixa' if si < 0.95 else 'média'} temporada).",
            )
    pos_en = ", ".join(f"{c} {money(v)}" for c, v in pos.head(2).items()) or "no positive contributors"
    pos_pt = ", ".join(f"{c} {money(v, 'pt')}" for c, v in pos.head(2).items()) or "sem contribuições positivas"
    neg_en = ", ".join(f"{c} {money(v)}" for c, v in neg.head(2).items())
    neg_pt = ", ".join(f"{c} {money(v, 'pt')}" for c, v in neg.head(2).items())
    answer = t(
        L,
        f"Consensus for {period} is {money(cons)}, {pct(growth, signed=True)} vs the same period last year "
        f"({money(ly)}). Statistical drivers by category: {pos_en}"
        + (f"; offsets: {neg_en}" if neg_en else "")
        + f". Commercial events add {money(events)}.",
        f"O consensus para {period} é {money(cons, 'pt')}, {pct(growth, 'pt', True)} vs mesmo período do ano "
        f"anterior ({money(ly, 'pt')}). Drivers estatísticos por categoria: {pos_pt}"
        + (f"; compensações: {neg_pt}" if neg_pt else "")
        + f". Eventos comerciais adicionam {money(events, 'pt')}.",
    )
    steps = [(t(L, "Last year", "Ano anterior"), ly, "total")]
    steps += [(c, float(v), "delta") for c, v in delta_cat.items()]
    steps += [(t(L, "Commercial events", "Eventos comerciais"), events, "delta"), ("Consensus", cons, "total")]
    insights = [seasonal_note] if seasonal_note else []
    if len(cust_delta):
        insights.append(
            t(
                L,
                f"Largest customer contribution: {cust_delta.index[-1]} ({money(cust_delta.iloc[-1])}); "
                f"largest drag: {cust_delta.index[0]} ({money(cust_delta.iloc[0])}).",
                f"Maior contribuição de cliente: {cust_delta.index[-1]} ({money(cust_delta.iloc[-1], 'pt')}); "
                f"maior queda: {cust_delta.index[0]} ({money(cust_delta.iloc[0], 'pt')}).",
            )
        )
    return _result(
        answer=answer,
        insights=insights,
        metrics=[
            {"label": "Consensus", "value": cons, "format": "currency"},
            {"label": t(L, "Last year", "Ano anterior"), "value": ly, "format": "currency"},
            {"label": t(L, "Growth", "Crescimento"), "value": growth, "format": "percent_signed"},
            {"label": t(L, "Commercial events", "Eventos comerciais"), "value": events, "format": "currency"},
        ],
        chart={
            "type": "waterfall",
            "format": "currency",
            "title": t(L, "Bridge: last year -> consensus", "Ponte: ano anterior -> consensus"),
            "x": [s[0] for s in steps],
            "series": [{"name": "Value", "data": [s[1] for s in steps]}],
            "kinds": [s[2] for s in steps],
        },
        recommendations=[
            t(
                L,
                "Validate the main category drivers with Marketing and confirm the commercial "
                "events with Key Accounts.",
                "Valide os principais drivers por categoria com "
                "Marketing e confirme os eventos comerciais com Key "
                "Accounts.",
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
        query=f"bridge(LY actual -> statistical by category -> events -> consensus, months={it.months or 'horizon'})",
    )


def h_risks(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = it.language
    alerts = build_alerts(ctx)
    if it.filters:
        alerts = [a for a in alerts if all(a["entity"].get(k) in (None, v) for k, v in it.filters.items())]
    top = alerts[:8]
    sev = {k: sum(1 for a in alerts if a["severity"] == k) for k in ("critical", "high", "medium", "low")}
    lst = "; ".join(
        f"{a['title']} - {a['entity'].get('customer', '')} {a['entity'].get('sku', '') or ''} "
        f"({a['magnitude']})".replace("  ", " ")
        for a in top[:3]
    )
    answer = t(
        L,
        f"{len(alerts)} alerts are open ({sev['critical']} critical, {sev['high']} high). Top items: {lst}.",
        f"Há {len(alerts)} alertas abertos ({sev['critical']} críticos, {sev['high']} altos). Principais: {lst}.",
    )
    return _result(
        answer=answer,
        insights=[a["explanation"] for a in top[:3]],
        metrics=[
            {"label": t(L, "Critical", "Críticos"), "value": sev["critical"], "format": "number", "tone": "red"},
            {"label": t(L, "High", "Altos"), "value": sev["high"], "format": "number", "tone": "orange"},
            {"label": t(L, "Medium", "Médios"), "value": sev["medium"], "format": "number"},
        ],
        table={
            "columns": ["Alert", "Entity", "Magnitude", "Impact (R$)"],
            "rows": [
                [
                    a["title"],
                    f"{a['entity'].get('customer', '')} {a['entity'].get('sku', '') or ''}".strip(),
                    a["magnitude"],
                    a["potential_impact"],
                ]
                for a in top
            ],
            "formats": ["text", "text", "text", "currency"],
        },
        recommendations=[a["recommendation"] for a in top[:2]],
        filters=it.filters,
        facts={
            "counts": sev,
            "top": [{k: a[k] for k in ("title", "entity", "magnitude", "potential_impact")} for a in top],
        },
        query="alerts.build_alerts(active run)",
    )


def h_model_distribution(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = it.language
    s = ctx.series[ctx.series["series_id"].isin(filter_ids(ctx, it.filters))]
    c = s["champion"].value_counts()
    answer = t(
        L,
        f"{c.index[0]} is the champion in {int(c.iloc[0])} of {len(s)} series ({pct(c.iloc[0] / len(s))}), "
        f"followed by {', '.join(f'{m} ({int(n)})' for m, n in c.iloc[1:4].items())}.",
        f"{c.index[0]} é campeão em {int(c.iloc[0])} de {len(s)} séries ({pct(c.iloc[0] / len(s), 'pt')}), "
        f"seguido por {', '.join(f'{m} ({int(n)})' for m, n in c.iloc[1:4].items())}.",
    )
    return _result(
        answer=answer,
        chart={
            "type": "bar",
            "format": "number",
            "title": t(L, "Champion models", "Modelos campeões"),
            "x": c.index.tolist(),
            "series": [{"name": t(L, "Series", "Séries"), "data": c.tolist()}],
        },
        metrics=[{"label": t(L, "Distinct champions", "Campeões distintos"), "value": len(c), "format": "number"}],
        filters=it.filters,
        facts={"champions": {k: int(v) for k, v in c.items()}, "total_series": len(s)},
        query="count(series) BY champion",
    )


def h_series_types(ctx: PlanningContext, it: Intent) -> dict[str, Any]:
    L = it.language
    s = ctx.series[ctx.series["series_id"].isin(filter_ids(ctx, it.filters))]
    c = s["series_type"].value_counts()
    answer = t(
        L,
        f"The portfolio has {len(s)} customer x SKU series: " + ", ".join(f"{k} {int(v)}" for k, v in c.items()) + ".",
        f"O portfólio tem {len(s)} séries cliente x SKU: " + ", ".join(f"{k} {int(v)}" for k, v in c.items()) + ".",
    )
    return _result(
        answer=answer,
        chart={
            "type": "bar",
            "format": "number",
            "title": t(L, "Series by demand pattern", "Séries por padrão de demanda"),
            "x": c.index.tolist(),
            "series": [{"name": t(L, "Series", "Séries"), "data": c.tolist()}],
        },
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
