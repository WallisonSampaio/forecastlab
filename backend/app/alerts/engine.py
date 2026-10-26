"""Alert Center: automatic, explained exceptions for the planner.

Every alert carries: issue, affected entity, magnitude, potential impact,
explanation and the recommended investigation.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from app import db
from app.services.context import Z90, PlanningContext, agg_sigma, clean
from app.services.ptbr import dec, model, money, pct, series_type

ALERT_TYPES = {
    "high_error": {"title": "Erro de forecast elevado", "color": "red", "icon": "🔴"},
    "severe_over": {"title": "Superestimação severa", "color": "red", "icon": "🔴"},
    "severe_under": {"title": "Subestimação severa", "color": "blue", "icon": "🔵"},
    "target_above_p90": {"title": "Meta acima do P90", "color": "orange", "icon": "🟠"},
    "structural_change": {"title": "Mudança estrutural no forecast", "color": "orange", "icon": "🟠"},
    "challenger_improving": {"title": "Desafiante melhorando", "color": "yellow", "icon": "🟡"},
    "opportunity": {"title": "Oportunidade comercial", "color": "green", "icon": "🟢"},
}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
MAX_PER_TYPE = 12

_cache: dict[tuple, list[dict[str, Any]]] = {}
# The context that owns the cached alerts. Compared by identity and kept alive, so a rebuilt context
# (e.g. after an override is saved) that reuses the old memory address never gets stale alerts.
_cache_owner: list[PlanningContext] = []


def _alert(
    kind: str,
    severity: str,
    entity: dict[str, Any],
    magnitude: str,
    impact: float,
    issue: str,
    explanation: str,
    recommendation: str,
    value: float | None = None,
) -> dict[str, Any]:
    meta = ALERT_TYPES[kind]
    key = "-".join(str(v) for v in entity.values())
    return clean(
        {
            "id": f"{kind}:{key}",
            "type": kind,
            "title": meta["title"],
            "color": meta["color"],
            "icon": meta["icon"],
            "severity": severity,
            "entity": entity,
            "issue": issue,
            "magnitude": magnitude,
            "value": value,
            "potential_impact": impact,
            "explanation": explanation,
            "recommendation": recommendation,
        }
    )


def build_alerts(ctx: PlanningContext) -> list[dict[str, Any]]:
    if not ctx.has_run:
        return []
    key = (ctx.version, ctx.run_id, id(ctx))
    if key in _cache and _cache_owner and _cache_owner[0] is ctx:
        return _cache[key]
    s = ctx.series.set_index("series_id")
    rev12 = ctx.forecast.assign(r=ctx.forecast["consensus"] * ctx.forecast["price"]).groupby("series_id")["r"].sum()
    total_rev = float(rev12.sum()) or 1.0
    horizon = f"{len(ctx.future_dates)} meses"
    alerts: list[dict[str, Any]] = []

    def ent(sid: str) -> dict[str, Any]:
        r = s.loc[sid]
        return {
            "series_id": sid,
            "customer": r["customer"],
            "sku": r["sku"],
            "product": r["product"],
            "region": r["region"],
        }

    # --- accuracy & bias ------------------------------------------------------------------
    cand = []
    for sid, r in s.iterrows():
        w, b, rev = r.get("wmape"), r.get("bias"), float(rev12.get(sid, 0.0))
        if rev / total_rev < 0.001:
            continue
        if pd.notna(w) and w > 0.35:
            sev = "critical" if w > 0.6 and rev / total_rev > 0.005 else "high"
            cand.append(
                (
                    "high_error",
                    rev * w,
                    _alert(
                        "high_error",
                        sev,
                        ent(sid),
                        f"WMAPE {pct(w)}",
                        rev * w,
                        f"Erro de {pct(w)} fora da amostra (backtest) no modelo campeão ({model(r['champion'])}).",
                        f"Série classificada como {series_type(r['series_type'])}; mesmo o melhor dos "
                        f"{len(json.loads(r['candidates']))} modelos candidatos erra, em média, {pct(w)}. "
                        f"Receita exposta no horizonte do forecast ({horizon}): {money(rev)}.",
                        "Verifique a qualidade dos dados (outliers, rupturas), confirme o padrão de demanda com Vendas "
                        "e considere gerenciar este item com estoque de segurança em vez de buscar precisão no forecast.",
                        w,
                    ),
                )
            )
        if pd.notna(b) and abs(b) > 0.15:
            kind = "severe_over" if b > 0 else "severe_under"
            cand.append(
                (
                    kind,
                    rev * abs(b),
                    _alert(
                        kind,
                        "high" if abs(b) > 0.25 else "medium",
                        ent(sid),
                        f"Viés {pct(b, signed=True)}",
                        rev * abs(b),
                        f"{'Superestimação' if b > 0 else 'Subestimação'} sistemática de {pct(abs(b))} no backtest.",
                        f"O forecast do modelo {model(r['champion'])} ficou consistentemente "
                        f"{'acima' if b > 0 else 'abaixo'} das vendas reais no backtest — sinal de uma "
                        "mudança de patamar à qual o modelo ainda está se adaptando.",
                        "Revise mudanças recentes de patamar, deslistagens ou novas listagens e valide os próximos "
                        "meses com o time da conta."
                        if b > 0
                        else "Verifique demanda não atendida (rupturas), ganho de distribuição ou crescimento ainda "
                        "não capturado pelo modelo.",
                        b,
                    ),
                )
            )

    # --- structural change / tracking signal ----------------------------------------------
    bt = ctx.backtest.sort_values("date")
    for sid, g in bt.groupby("series_id"):
        if sid not in s.index:
            continue
        recent = g.tail(6)
        err = (recent["forecast"] - recent["actual"]).to_numpy(float)
        mad = np.mean(np.abs(err)) if len(err) else 0
        ts = float(err.sum() / mad) if mad else 0.0
        r = s.loc[sid]
        rev = float(rev12.get(sid, 0.0))
        if (abs(ts) >= 4.5 or r["series_type"] == "Structural Change") and rev / total_rev > 0.001:
            cand.append(
                (
                    "structural_change",
                    rev * 0.1,
                    _alert(
                        "structural_change",
                        "medium",
                        ent(sid),
                        f"Sinal de rastreamento {dec(ts, 1, signed=True)}",
                        rev * 0.1,
                        "O comportamento da demanda mudou recentemente."
                        if r["series_type"] != "Structural Change"
                        else "Uma mudança de patamar foi detectada no histórico.",
                        "O sinal de rastreamento (tracking signal) dos últimos 6 meses do backtest é "
                        f"{dec(ts, 1, signed=True)} (|TS| ≥ 4,5 indica viés persistente). "
                        f"Tipo da série: {series_type(r['series_type'])}.",
                        "Confirme a causa (mudança de preço, concorrente, listagem) e decida entre encurtar a janela "
                        "de treino ou registrar um ajuste comercial.",
                        ts,
                    ),
                )
            )

    # --- challenger improving -------------------------------------------------------------
    reg = db.query_df(
        "SELECT series_id, model, fold_wmape, champion_flag, challenger_flag FROM model_registry "
        "WHERE run_id = ? AND (champion_flag OR challenger_flag)",
        [ctx.run_id],
    )
    for sid, g in reg.groupby("series_id"):
        ch = g[g["champion_flag"]]
        cl = g[g["challenger_flag"]]
        if ch.empty or cl.empty or sid not in s.index:
            continue
        fw_ch = json.loads(ch["fold_wmape"].iloc[0] or "[]")
        fw_cl = json.loads(cl["fold_wmape"].iloc[0] or "[]")
        if len(fw_ch) >= 2 and len(fw_cl) >= 2 and fw_cl[-1] < fw_ch[-1] * 0.8 and fw_cl[-2] < fw_ch[-2]:
            rev = float(rev12.get(sid, 0.0))
            if rev / total_rev < 0.002:
                continue
            cand.append(
                (
                    "challenger_improving",
                    rev * (fw_ch[-1] - fw_cl[-1]),
                    _alert(
                        "challenger_improving",
                        "low",
                        ent(sid),
                        f"WMAPE {pct(fw_cl[-1])} vs {pct(fw_ch[-1])} do campeão",
                        rev * (fw_ch[-1] - fw_cl[-1]),
                        f"O desafiante {model(cl['model'].iloc[0])} superou o campeão {model(ch['model'].iloc[0])} "
                        "nas duas janelas de validação mais recentes.",
                        "No backtest completo o campeão ainda vence, mas as janelas recentes favorecem o desafiante — "
                        "o padrão de demanda pode estar mudando.",
                        "Monitore o próximo ciclo; se o desafiante continuar vencendo, promova-o a campeão.",
                        fw_cl[-1],
                    ),
                )
            )

    # --- target above P90 / opportunity (customer level) -----------------------------------------
    if not ctx.plan.empty:
        f = ctx.forecast.merge(ctx.series[["series_id", "customer", "region"]], on="series_id")
        f = f.assign(cons=f["consensus"] * f["price"], sig=f["sigma"] * f["price"], base=f["p50"] * f["price"])
        p = ctx.plan[ctx.plan["date"].isin(ctx.future_dates)].merge(
            ctx.series[["series_id", "customer"]], on="series_id"
        )
        for cust, g in f.groupby("customer"):
            pc = p[p["customer"] == cust]
            target, budget = float(pc["target_revenue"].sum()), float(pc["budget_revenue"].sum())
            cons, base = float(g["cons"].sum()), float(g["base"].sum())
            sig = agg_sigma(g["sig"]) * (cons / base if base else 1)
            p90 = cons + Z90 * sig
            entity = {"customer": cust, "region": g["region"].iloc[0]}
            if target > p90:
                cand.append(
                    (
                        "target_above_p90",
                        target - cons,
                        _alert(
                            "target_above_p90",
                            "high",
                            entity,
                            f"Meta {pct(target / cons - 1 if cons else None, signed=True)} vs consenso",
                            target - cons,
                            f"A meta de vendas do horizonte ({horizon}) está acima do P90 do forecast.",
                            f"Meta {money(target)} vs consenso {money(cons)} (P90 {money(p90)}). Menos de 1 em cada "
                            "10 cenários plausíveis atinge essa meta sem novas ações comerciais.",
                            "Rode a análise de Viabilidade da Meta, recalibre a meta ou documente as alavancas de "
                            "crescimento (distribuição, promoções) necessárias para fechar o gap.",
                            target / cons - 1 if cons else None,
                        ),
                    )
                )
            if budget and cons > budget * 1.10:
                cand.append(
                    (
                        "opportunity",
                        cons - budget,
                        _alert(
                            "opportunity",
                            "low",
                            entity,
                            f"Consenso {pct(cons / budget - 1, signed=True)} vs orçamento",
                            cons - budget,
                            "A demanda está acima do orçamento.",
                            f"Consenso {money(cons)} vs orçamento {money(budget)}. O momento positivo (tendência, "
                            "distribuição ou crescimento do canal) não está refletido no plano.",
                            "Garanta abastecimento para a demanda adicional, avalie elevar a meta e replique o que está "
                            "funcionando.",
                            cons / budget - 1,
                        ),
                    )
                )

    by_type: dict[str, list[tuple[float, dict]]] = {}
    for kind, impact, a in cand:
        by_type.setdefault(kind, []).append((impact, a))
    for items in by_type.values():
        items.sort(key=lambda x: -x[0])
        alerts.extend(a for _, a in items[:MAX_PER_TYPE])
    alerts.sort(key=lambda a: (SEVERITY_ORDER[a["severity"]], -(a["potential_impact"] or 0)))
    _cache.clear()
    _cache_owner[:] = [ctx]
    _cache[key] = alerts
    return alerts


def filter_alerts(ctx: PlanningContext, alerts: list[dict[str, Any]], ids) -> list[dict[str, Any]]:
    """Alerts inside a filtered scope (``ids`` = series ids from ``context.filter_ids``).

    Series alerts are kept when their series is in scope; customer alerts (target above P90, opportunity)
    when the customer has at least one series in scope. With every series in scope the list is unchanged.
    """
    in_scope = set(ids)
    if len(in_scope) >= len(ctx.series):
        return alerts
    customers = set(ctx.series.loc[ctx.series["series_id"].isin(in_scope), "customer"])
    out = []
    for a in alerts:
        entity = a.get("entity") or {}
        sid = entity.get("series_id")
        if (sid in in_scope) if sid is not None else (entity.get("customer") in customers):
            out.append(a)
    return out


def summary(alerts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(alerts),
        "by_severity": {k: sum(1 for a in alerts if a["severity"] == k) for k in SEVERITY_ORDER},
        "by_type": {k: sum(1 for a in alerts if a["type"] == k) for k in ALERT_TYPES},
    }
