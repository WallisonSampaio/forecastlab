"""Target Feasibility Engine: "Is this target realistic?"

The consensus forecast is treated as a distribution N(consensus, sigma),
where sigma is aggregated from out-of-sample backtest errors. The target is
then judged on:

* probability of achieving it,
* where it sits vs. P10 / P50 / P90,
* required growth vs. historical growth and volatility,
* customer potential (addressable headroom),
* incremental demand already planned through commercial events.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from app.scenarios.elasticity import estimate_elasticities, for_category
from app.services.context import Z90, PlanningContext, clean, filter_ids, horizon_totals
from app.services.ptbr import measure as fmt_measure
from app.services.ptbr import pct

# Largest single-lever move considered commercially plausible within a planning year.
PLAUSIBLE = {"Distribution": 0.20, "Price": 0.08, "Marketing": 0.50}

CLASSES = {
    "REALISTIC": {"color": "green", "emoji": "🟢", "label": "Realista"},
    "STRETCH": {"color": "yellow", "emoji": "🟡", "label": "Desafiadora"},
    "AGGRESSIVE": {"color": "red", "emoji": "🔴", "label": "Agressiva"},
    "UNDERESTIMATED": {"color": "blue", "emoji": "🔵", "label": "Subestimada"},
}


def classify(target: float, mean: float, sigma: float, p10: float, p90: float) -> tuple[str, float]:
    """Classification from the probability that demand reaches the target."""
    if target <= 0:
        return "UNDERESTIMATED", 1.0
    if sigma <= 0:
        prob = 1.0 if mean >= target else 0.0
    else:
        prob = float(1 - norm.cdf((target - mean) / sigma))
    if target <= p10 or prob >= 0.9:
        return "UNDERESTIMATED", prob
    if prob >= 0.5:
        return "REALISTIC", prob
    if prob >= 0.2 and target <= p90:
        return "STRETCH", prob
    return "AGGRESSIVE", prob


def _potential(ctx: PlanningContext, ids: pd.Index) -> float | None:
    """Annual unit potential attributable to the selected series.

    Customer potential is shared across a customer's SKUs in proportion to
    each series' share of the customer's last-12-month volume.
    """
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    if "customer_potential" not in s or s["customer_potential"].isna().all():
        return None
    ltm = ctx.actuals[ctx.actuals["date"].isin(ctx.ltm_dates)].merge(
        ctx.series[["series_id", "customer"]], on="series_id"
    )
    cust_total = ltm.groupby("customer")["units"].sum()
    series_ltm = ltm.groupby("series_id")["units"].sum()
    total = 0.0
    for r in s.itertuples():
        if pd.isna(r.customer_potential) or not cust_total.get(r.customer):
            continue
        total += float(r.customer_potential) * float(series_ltm.get(r.series_id, 0.0)) / float(cust_total[r.customer])
    return total or None


def assess(
    ctx: PlanningContext,
    filters: dict[str, Any] | None = None,
    months: list[str] | None = None,
    measure: str = "revenue",
) -> dict[str, Any]:
    if not ctx.has_run:
        return {"available": False, "message": "Execute um forecast primeiro."}
    ids = filter_ids(ctx, filters)
    sel_months = (
        pd.DatetimeIndex([pd.Timestamp(m).to_period("M").to_timestamp() for m in months])
        if months
        else ctx.future_dates
    )
    sel_months = sel_months[sel_months.isin(ctx.future_dates)]
    if len(sel_months) == 0:
        return {"available": False, "message": "Os meses selecionados estão fora do horizonte do forecast."}
    t = horizon_totals(ctx, ids, measure, sel_months)
    target = t.get("target")
    if target is None:
        return {"available": False, "message": "Não há meta disponível para esta seleção."}
    cons, base, budget = t["consensus"], t["base"], t.get("budget") or 0.0
    sigma_c = t["sigma"] * (cons / base if base else 1.0)
    p10c, p90c = max(0.0, cons - Z90 * sigma_c), cons + Z90 * sigma_c
    cls, prob = classify(target, cons, sigma_c, p10c, p90c)

    col = "revenue" if measure == "revenue" else "units"
    a = ctx.actuals[ctx.actuals["series_id"].isin(ids)]
    ly = float(a[a["date"].isin(sel_months - pd.DateOffset(years=1))][col].sum())
    hist_growth = (t["actual_ltm"] / t["actual_prior_ltm"] - 1) if t["actual_prior_ltm"] else None
    required_growth = (target / ly - 1) if ly else None
    forecast_growth = (cons / ly - 1) if ly else None
    monthly = a[a["date"].isin(ctx.ltm_dates)].groupby("date")[col].sum()
    volatility = float(monthly.std() / monthly.mean()) if len(monthly) > 2 and monthly.mean() else None

    reasons: list[str] = []
    capacity_ratio = None
    potential = _potential(ctx, ids)
    if potential:
        target_units = horizon_totals(ctx, ids, "units", sel_months).get("target") or 0.0
        annualized = target_units * 12 / len(sel_months)
        capacity_ratio = annualized / potential
        if capacity_ratio > 1.0:
            reasons.append(f"A meta implica {pct(capacity_ratio)} do potencial endereçável dos clientes")
            cls = "AGGRESSIVE"
    if required_growth is not None and hist_growth is not None and prob < 0.5:
        if required_growth > max(2 * abs(hist_growth), hist_growth + 0.15):
            reasons.append(
                f"O crescimento necessário de {pct(required_growth, 1, signed=True)} está muito acima do "
                f"crescimento histórico de {pct(hist_growth, 1, signed=True)}"
            )
            cls = "AGGRESSIVE" if cls == "STRETCH" else cls
    if target > p90c:
        reasons.append("A meta está acima do P90 do forecast de consenso")
    elif target > cons:
        reasons.append("A meta está acima do consenso (P50), mas dentro da faixa P10-P90")
    elif target < p10c:
        reasons.append("A meta está abaixo do P10 do forecast de consenso - provavelmente subestimada")
    else:
        reasons.append("A meta está igual ou abaixo do forecast de consenso")
    if t.get("incremental"):
        reasons.append(
            f"O consenso já inclui {fmt_measure(t['incremental'], measure)} de eventos comerciais planejados"
        )

    gap = target - cons
    gap_pct = gap / cons if cons else None
    levers = _levers(ctx, ids, gap_pct, cons, measure, len(sel_months)) if gap > 0 else []
    return clean(
        {
            "available": True,
            "measure": measure,
            "months": [m.strftime("%Y-%m-%d") for m in sel_months],
            "classification": cls,
            "display": CLASSES[cls],
            "probability": prob,
            "target": target,
            "budget": budget,
            "statistical": base,
            "consensus": cons,
            "p10": p10c,
            "p50": cons,
            "p90": p90c,
            "statistical_p10": t["p10"],
            "statistical_p90": t["p90"],
            "planned_events": t.get("incremental"),
            "last_year": ly,
            "historical_growth": hist_growth,
            "required_growth": required_growth,
            "forecast_growth": forecast_growth,
            "volatility_cv": volatility,
            "potential_units": potential,
            "capacity_ratio": capacity_ratio,
            "calibration": {
                "required_incremental_vs_budget": (target / budget - 1) if budget else None,
                "gap_vs_consensus": gap,
                "gap_vs_consensus_pct": gap_pct,
                "budget_vs_consensus_pct": (budget / cons - 1) if cons else None,
            },
            "reasons": reasons,
            "levers": levers,
            "recommendation": _recommendation(cls, gap, gap_pct, measure),
        }
    )


def _levers(
    ctx: PlanningContext, ids: pd.Index, gap_pct: float | None, cons: float, measure: str, n_months: int
) -> list[dict[str, Any]]:
    """Translate the gap into the lever movement that would close it (alone)."""
    if not gap_pct or gap_pct <= 0:
        return []
    el = estimate_elasticities(ctx.version)
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    w = ctx.forecast[ctx.forecast["series_id"].isin(ids)].groupby("series_id")["consensus"].sum()
    cats = s.set_index("series_id")["category"]
    weights = w.groupby(cats.reindex(w.index)).sum()
    weights = weights / weights.sum() if weights.sum() else weights

    def avg(key: str) -> float:
        return (
            float(sum(weights.get(c, 0) * for_category(el, c)[key] for c in weights.index))
            if len(weights)
            else float(for_category(el, "__all__")[key])
        )

    g = 1 + gap_pct
    e_d, e_p, e_m, promo = (
        avg("distribution_elasticity"),
        avg("price_elasticity"),
        avg("marketing_elasticity"),
        avg("promo_uplift"),
    )
    out = [
        {
            "lever": "Distribution",
            "required_change": g ** (1 / e_d) - 1 if e_d > 0 else None,
            "elasticity": e_d,
            "note": "Aumento necessário na distribuição numérica",
        },
        {
            "lever": "Price",
            "required_change": g ** (1 / e_p) - 1 if e_p < 0 else None,
            "elasticity": e_p,
            "note": "Redução de preço necessária (apenas efeito em volume; o impacto em receita é diferente)",
        },
        {
            "lever": "Marketing",
            "required_change": g ** (1 / e_m) - 1 if e_m > 0 else None,
            "elasticity": e_m,
            "note": "Aumento necessário no investimento em marketing",
        },
    ]
    if promo > 0 and n_months:
        months_needed = gap_pct * n_months / promo
        out.append(
            {
                "lever": "Promotions",
                "required_change": months_needed,
                "elasticity": promo,
                "note": f"Meses com promoção necessários na seleção (uplift de {pct(promo)} por mês promocional)",
            }
        )
    for o in out:
        rc = o["required_change"]
        o["plausible"] = (
            rc is not None
            and math.isfinite(rc)
            and (abs(rc) <= PLAUSIBLE[o["lever"]] if o["lever"] != "Promotions" else rc <= n_months / 3)
        )
    return out


def _recommendation(cls: str, gap: float, gap_pct: float | None, measure: str) -> str:
    gap_txt = fmt_measure(gap, measure)
    if cls == "UNDERESTIMATED":
        return (
            "A meta está abaixo do resultado mais provável. Considere elevá-la ou realocar o esforço comercial "
            "para onde as metas estão agressivas."
        )
    if cls == "REALISTIC":
        return "A meta é sustentada pelo forecast de consenso. Proteja a base: disponibilidade e execução."
    if cls == "STRETCH":
        return (
            f"Fechar o gap de {pct(gap_pct, 1, signed=True)} ({gap_txt}) exige ações comerciais incrementais "
            "(distribuição, promoções ou marketing). Valide o plano na reunião de S&OP."
        )
    if gap <= 0:
        return (
            "A meta está próxima do forecast, mas exige mais do que o potencial endereçável dos clientes. "
            "Revise a meta ou o potencial cadastrado antes de comprometê-la."
        )
    return (
        f"A meta exige {pct(gap_pct, 1, signed=True)} sobre o consenso ({gap_txt}). É estatisticamente improvável "
        "sem mudanças estruturais - recalibre a meta ou comprometa alavancas de crescimento concretas."
    )


def feasibility_by(
    ctx: PlanningContext, dimension: str, filters: dict[str, Any] | None = None, measure: str = "revenue"
) -> list[dict[str, Any]]:
    if not ctx.has_run:
        return []
    ids = filter_ids(ctx, filters)
    s = ctx.series[ctx.series["series_id"].isin(ids)]
    rows = []
    for member, g in s.groupby(dimension):
        t = horizon_totals(ctx, pd.Index(g["series_id"]), measure)
        if not t.get("target"):
            continue
        cons, base = t["consensus"], t["base"]
        sig = t["sigma"] * (cons / base if base else 1.0)
        p10c, p90c = max(0.0, cons - Z90 * sig), cons + Z90 * sig
        cls, prob = classify(t["target"], cons, sig, p10c, p90c)
        rows.append(
            clean(
                {
                    "member": member,
                    "target": t["target"],
                    "budget": t.get("budget"),
                    "consensus": cons,
                    "p10": p10c,
                    "p90": p90c,
                    "probability": prob,
                    "classification": cls,
                    "gap_vs_target": cons - t["target"],
                    "gap_vs_target_pct": (cons / t["target"] - 1),
                    "required_growth": (t["target"] / t["actual_ltm"] - 1) if t["actual_ltm"] else None,
                }
            )
        )
    return sorted(rows, key=lambda r: r["probability"] if r["probability"] is not None else 0)


def probability_curve(mean: float, sigma: float, n: int = 41) -> list[dict[str, float]]:
    if sigma <= 0:
        return []
    xs = np.linspace(max(0.0, mean - 3 * sigma), mean + 3 * sigma, n)
    return [
        {"x": float(x), "pdf": float(norm.pdf(x, mean, sigma)), "p_exceed": float(1 - norm.cdf(x, mean, sigma))}
        for x in xs
    ]
