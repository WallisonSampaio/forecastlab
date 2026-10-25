"""AI Demand Analyst orchestration.

User question
    -> intent extraction (rules, LLM fallback)
    -> semantic query / forecast, scenario, S&OP and FVA engines
    -> structured result (numbers computed deterministically)
    -> LLM explanation (optional, grounded) or deterministic NLG
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.services.context import PlanningContext, clean

from . import llm
from .handlers import HANDLERS
from .intents import (
    INTENTS,
    Intent,
    detect_language,
    extract_dimension,
    extract_entities,
    extract_levers,
    extract_months,
    parse,
)
from .nlg import t

log = logging.getLogger("forecastlab.ai")

SUGGESTIONS = {
    "en": [
        "What is driving forecast growth in July?",
        "Which SKUs have the worst forecast accuracy?",
        "Which customers are overforecasted?",
        "Is December target realistic?",
        "Which model performs best for SKU-20102?",
        "What happens if distribution increases by 10%?",
        "Which commercial overrides reduced accuracy?",
        "Where are we below budget?",
        "What are the main risks?",
    ],
    "pt": [
        "O que está impulsionando o crescimento do forecast em julho?",
        "Quais SKUs têm a pior acurácia?",
        "Quais clientes estão superestimados?",
        "A meta de dezembro é realista?",
        "O que acontece se a distribuição aumentar 10%?",
        "Quais ajustes comerciais pioraram a acurácia?",
    ],
}


def _members(ctx: PlanningContext) -> dict[str, Any]:
    s = ctx.series
    return {
        "region": sorted(s["region"].dropna().unique().tolist()),
        "channel": sorted(s["channel"].dropna().unique().tolist()),
        "customer": sorted(s["customer"].dropna().unique().tolist()),
        "category": sorted(s["category"].dropna().unique().tolist()),
        "brand": sorted(s["brand"].dropna().unique().tolist()),
        "sku": sorted(s["sku"].dropna().unique().tolist()),
        "product_map": s[["sku", "product"]].drop_duplicates().values.tolist(),
    }


def ask(
    ctx: PlanningContext, question: str, filters: dict[str, Any] | None = None, use_llm: bool = True
) -> dict[str, Any]:
    t0 = time.perf_counter()
    question = (question or "").strip()
    lang = detect_language(question)
    if not ctx.has_run:
        return _wrap(
            ctx,
            question,
            lang,
            {
                "answer": t(
                    lang,
                    "Run a forecast first - the analyst only explains computed results.",
                    "Execute um forecast primeiro - o analista só explica resultados calculados.",
                ),
            },
            None,
            "none",
            t0,
        )
    members = _members(ctx)
    intent = parse(question, members, list(ctx.future_dates), ctx.last_actual)
    llm_status = llm.status() if use_llm else {"available": False}
    if intent is None and llm_status.get("available"):
        try:
            c = llm.classify_intent(question, INTENTS)
            if c.get("intent") in HANDLERS:
                intent = Intent(
                    name=c["intent"],
                    language=lang,
                    months=extract_months(question, list(ctx.future_dates), ctx.last_actual),
                    dimension=c.get("dimension") or extract_dimension(question),
                    filters=extract_entities(question, members),
                    levers=extract_levers(question),
                    direction=c.get("direction"),
                    confidence=0.6,
                    source="llm",
                )
        except Exception as exc:
            log.warning("LLM intent classification failed: %s", exc)
    if intent is None:
        return _wrap(
            ctx,
            question,
            lang,
            {
                "answer": t(
                    lang,
                    "I can answer questions about forecast accuracy, bias, drivers, targets, scenarios, "
                    "budget gaps, models, overrides (FVA) and risks. Try one of the suggestions.",
                    "Posso responder sobre acurácia, viés, drivers, metas, cenários, gaps de orçamento, modelos, "
                    "ajustes (FVA) e riscos. Experimente uma das sugestões.",
                ),
                "recommendations": SUGGESTIONS[lang][:4],
            },
            None,
            "none",
            t0,
        )

    # Page-level filters complement entities found in the question.
    for k, v in (filters or {}).items():
        if v and k not in intent.filters:
            intent.filters[k] = v
    result = HANDLERS[intent.name](ctx, intent)
    engine = "rule-based NLG"
    grounding: dict[str, Any] = {"checked": False}
    if llm_status.get("available") and use_llm:
        try:
            out = llm.explain(question, result["facts"], result, intent.language)
            allowed = llm.allowed_numbers(
                result["facts"],
                result["metrics"],
                result.get("table"),
                result.get("chart"),
                result["answer"],
                result["insights"],
            )
            text = " ".join([out["answer"], *out["insights"], *out["recommendations"]])
            bad = llm.grounding_violations(text, allowed)
            grounding = {"checked": True, "violations": bad[:10], "passed": not bad}
            if not bad and out["answer"]:
                result.update(
                    answer=out["answer"],
                    insights=out["insights"] or result["insights"],
                    recommendations=out["recommendations"] or result["recommendations"],
                )
                engine = f"ollama:{llm_status['model']}"
            else:
                engine = "rule-based NLG (LLM output rejected by grounding check)"
        except Exception as exc:
            log.warning("LLM explanation failed: %s", exc)
            engine = "rule-based NLG (LLM unavailable)"
    return _wrap(ctx, question, intent.language, result, intent, engine, t0, grounding)


def _wrap(
    ctx: PlanningContext,
    question: str,
    lang: str,
    result: dict[str, Any],
    intent: Intent | None,
    engine: str,
    t0: float,
    grounding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = {
        "answer": "",
        "insights": [],
        "metrics": [],
        "chart": None,
        "table": None,
        "recommendations": [],
        "filters": {},
    }
    base.update({k: v for k, v in result.items() if k in base})
    base["meta"] = {
        "question": question,
        "language": lang,
        "intent": intent.as_dict() if intent else None,
        "engine": engine,
        "grounding": grounding or {"checked": False},
        "query": result.get("query"),
        "run_id": ctx.run_id,
        "dataset_version": ctx.version,
        "latency_ms": round((time.perf_counter() - t0) * 1000),
    }
    return clean(base)
