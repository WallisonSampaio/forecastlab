"""AI Demand Analyst orchestration.

User question (PT-BR or EN)
    -> intent scoring + entity / period / lever extraction (deterministic rules)
    -> semantic query / forecast, scenario, S&OP and FVA engines
    -> structured result (numbers computed deterministically) + deterministic NLG
    -> returned at once; the page may then ask the local LLM to refine the wording in the
       background (``/api/ai/narrate``, numeric grounding guard)

``ask`` never waits for the LLM. Only an explicit ``route_with_llm`` request (a question the rules
did not understand) calls the local model, to classify the intent; the result is validated against
the known intents and entities before the normal handler runs.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.services.context import PlanningContext, clean

from . import llm, narration
from .handlers import HANDLERS, RANK_DIMS
from .intents import (
    BACKTEST_INTENTS,
    INTENTS,
    STOP_TOKENS,
    Intent,
    _to_past,
    _tokens,
    detect_language,
    extract_entities,
    extract_levers,
    extract_months,
    parse,
)
from .nlg import t

log = logging.getLogger("forecastlab.ai")

SUGGESTIONS = {
    "pt": [
        "Quanto vamos vender em dezembro?",
        "A meta de dezembro é realista?",
        "Como está o cliente Atlas Hipermercados?",
        "Qual o WMAPE da Atlas?",
        "Quais clientes estão superestimados?",
        "O que acontece se a distribuição aumentar 10%?",
        "Onde estamos abaixo do orçamento?",
        "Por que o forecast de julho cresce?",
        "Quais ajustes comerciais pioraram a acurácia?",
        "Quais os principais riscos?",
    ],
    "en": [
        "How much will we sell in December?",
        "Is the December target realistic?",
        "How is customer Atlas Hipermercados doing?",
        "What is the WMAPE for Atlas?",
        "Which customers are overforecasted?",
        "What happens if distribution increases by 10%?",
        "Where are we below budget?",
        "What is driving forecast growth in July?",
        "Which commercial overrides reduced accuracy?",
        "What are the main risks?",
    ],
}

# Shown when the question is not understood (one per family of questions).
FALLBACK_EXAMPLES = {
    "pt": [
        "Quanto vamos vender no próximo trimestre?",
        "A meta de dezembro é realista?",
        "Qual o viés do cliente Atlas?",
        "E se o preço cair 5% no Sul?",
    ],
    "en": [
        "How much will we sell next quarter?",
        "Is the December target realistic?",
        "What is the bias for customer Atlas?",
        "What if price drops 5% in the South?",
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


def _not_understood(question: str, lang: str, llm_tried: bool = False) -> dict[str, Any]:
    q = question.strip() or "…"
    lead_en = f"I could not understand “{q}”" + (", not even with the local AI" if llm_tried else "")
    lead_pt = f"Não consegui entender “{q}”" + (", nem com a ajuda da IA local" if llm_tried else "")
    return {
        "answer": t(
            lang,
            f"{lead_en}: I did not recognize any metric (target, forecast, accuracy, bias, "
            "budget...), period, customer, product, region or channel in it. I can answer about sales forecast, "
            "targets, accuracy and bias, budget gaps, what-if simulations, models, commercial overrides (FVA), "
            "risks, and give an overview of any customer, region, channel, category, brand or SKU. Try one of "
            "these questions:",
            f"{lead_pt}: não reconheci na pergunta nenhum indicador (meta, previsão, acurácia, "
            "viés, orçamento…), período, cliente, produto, região ou canal. Posso responder sobre previsão de "
            "vendas, metas, acurácia e viés, gaps vs orçamento, simulações what-if, modelos, ajustes comerciais "
            "(FVA), riscos e dar uma visão de qualquer cliente, região, canal, categoria, marca ou SKU. "
            "Experimente uma destas perguntas:",
        ),
        "recommendations": FALLBACK_EXAMPLES["en" if lang == "en" else "pt"],
    }


# ------------------------------------------------------------------------------ clarification
# A word shared by several members ("varejo" → Varejo Moderno, Varejo Tradicional) is ambiguous on
# purpose in the entity rules; instead of the generic help we ask which member the user meant.
_CLARIFY_DIMS = ("channel", "region", "category", "customer", "brand")
_CLARIFY_PT = {
    "channel": "o canal",
    "region": "a região",
    "category": "a categoria",
    "customer": "o cliente",
    "brand": "a marca",
}
_CLARIFY_EN = {
    "channel": "channel",
    "region": "region",
    "category": "category",
    "customer": "customer",
    "brand": "brand",
}
_CLARIFY_MAX = 6


def _clarify(question: str, lang: str, members: dict[str, Any]) -> dict[str, Any] | None:
    words = [w for w in dict.fromkeys(_tokens(question)) if len(w) >= 4 and w not in STOP_TOKENS]
    for word in words:
        hits = [(dim, m) for dim in _CLARIFY_DIMS for m in members.get(dim, []) if word in _tokens(str(m))]
        if not 2 <= len(hits) <= _CLARIFY_MAX:
            continue
        names = [m for _, m in hits]
        listed_pt = ", ".join(names[:-1]) + f" ou {names[-1]}"
        listed_en = ", ".join(names[:-1]) + f" or {names[-1]}"
        return {
            "answer": t(
                lang,
                f"“{word}” matches more than one member: {listed_en}. Which one do you want to analyse?",
                f"“{word}” corresponde a mais de um item: {listed_pt}. Qual deles você quer analisar?",
            ),
            "recommendations": [
                t(lang, f"How is {_CLARIFY_EN[d]} {m} doing?", f"Como está {_CLARIFY_PT[d]} {m}?") for d, m in hits
            ],
        }
    return None


# ------------------------------------------------------------------------------ LLM routing
_DIRECTIONS = {
    "bias_ranking": ("over", "under", "abs"),
    "worst_accuracy": ("best", "worst"),
}
_METRICS = ("wmape", "accuracy", "bias", "rmse", "mae")


def _mentions(raw: Any, limit: int = 3) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(x).strip()[:80] for x in raw if isinstance(x, str) and str(x).strip()][:limit]


def validate_llm_intent(
    ctx: PlanningContext, raw: dict[str, Any], question: str, lang: str, members: dict[str, Any]
) -> Intent | None:
    """Turn a raw LLM classification into an ``Intent`` - or ``None`` when it cannot be trusted.

    Nothing from the model is used as is: the intent must be a known handler, the dimension,
    direction and metric must be known codes, and entity / month mentions only count when the
    deterministic extractors resolve them to real hierarchy members and horizon months.
    """
    name = raw.get("intent") if isinstance(raw, dict) else None
    if not isinstance(name, str) or name not in HANDLERS:
        return None
    filters: dict[str, Any] = {}
    for mention in [question, *_mentions(raw.get("entities"))]:
        for k, v in extract_entities(mention, members).items():
            filters.setdefault(k, v)
    horizon, last = list(ctx.future_dates), ctx.last_actual
    months = extract_months(question, horizon, last)
    if not months:
        for mention in _mentions(raw.get("months")):
            months = extract_months(mention, horizon, last)
            if months:
                break
    if name in BACKTEST_INTENTS and months:
        months = _to_past(months, last)
    dim = raw.get("dimension") if raw.get("dimension") in RANK_DIMS else None
    if dim in filters:
        dim = None
    allowed_dirs = _DIRECTIONS.get(name, ())
    direction = raw.get("direction") if raw.get("direction") in allowed_dirs else None
    metric = raw.get("metric") if raw.get("metric") in _METRICS else None
    levers = extract_levers(question)

    if name == "entity_overview" and not filters:
        return None  # an overview of what?
    if name == "bias_ranking":
        dim, direction = dim or "customer", direction or "abs"
    elif name == "worst_accuracy":
        dim, direction = dim or "sku", direction or "worst"
    elif name == "budget_gap":
        dim = dim or ("sku" if "customer" in filters else "customer")
    elif name == "fva_overrides":
        dim = dim if dim == "customer" else None
    return Intent(
        name=name,
        language=lang,
        months=months,
        dimension=dim,
        filters=filters,
        levers=levers,
        direction=direction,
        metric=metric,
        period="month" if months else None,
        confidence=0.6,
        source="llm",
    )


def _route_with_llm(
    ctx: PlanningContext, question: str, lang: str, members: dict[str, Any]
) -> tuple[Intent | None, dict[str, Any]]:
    t0 = time.perf_counter()
    info: dict[str, Any] = {"tried": True, "status": "unavailable", "model": None, "raw_intent": None}
    st = llm.status(max_wait=3.0)
    if not st.get("available"):
        info["reason"] = st.get("reason")
    else:
        info["model"] = st["model"]
        gen = narration.new_generation()  # one CPU worker: a running narration gives way to this question
        try:
            raw = llm.classify_intent(
                question, INTENTS, model=st["model"], should_cancel=lambda: narration.is_stale(gen)
            )
            info["raw_intent"] = raw.get("intent") if isinstance(raw.get("intent"), str) else None
            intent = validate_llm_intent(ctx, raw, question, lang, members)
            info["status"] = "ok" if intent else "unknown"
            info["elapsed_s"] = round(time.perf_counter() - t0, 1)
            return intent, info
        except llm.LLMTimeout:
            info["status"] = "timeout"
        except llm.LLMCancelled:
            info["status"] = "cancelled"
        except (llm.LLMError, ValueError, TypeError, AttributeError) as exc:
            log.warning("LLM intent classification failed: %s", exc)
            info["status"] = "error"
    info["elapsed_s"] = round(time.perf_counter() - t0, 1)
    return None, info


# ------------------------------------------------------------------------------ ask
_NO_NARRATION_REASON = {
    "no_run": "Não há resultados calculados para refinar.",
    "not_understood": "A pergunta não foi reconhecida; não há resposta calculada para refinar.",
    "off": "Refinamento pela IA local desativado nesta pergunta.",
    "list": "Resposta em formato de ranking ou lista: a versão calculada já é a mais fiel.",
    "what_if": "Simulação what-if: a versão calculada já separa a alavanca do resultado e é a mais fiel.",
}


def _narration(use_llm: bool, kind: str | None = None, intent: str | None = None) -> dict[str, Any]:
    if kind:
        return {"available": False, "model": None, "reason": _NO_NARRATION_REASON[kind]}
    if intent is not None and intent not in narration.NARRATABLE_INTENTS:
        reason = _NO_NARRATION_REASON["what_if" if intent == "what_if" else "list"]
        return {"available": False, "model": None, "reason": reason}
    if not use_llm:
        return {"available": False, "model": None, "reason": _NO_NARRATION_REASON["off"]}
    st = llm.status(max_wait=0.6)  # bounded: /api/ai/ask must answer in < 1,5 s
    if st.get("available"):
        return {"available": True, "model": st["model"], "reason": None}
    return {"available": False, "model": None, "reason": st.get("reason") or "A IA local não está disponível."}


def ask(
    ctx: PlanningContext,
    question: str,
    filters: dict[str, Any] | None = None,
    use_llm: bool = True,
    route_with_llm: bool = False,
) -> dict[str, Any]:
    """Deterministic answer, at once. The LLM is only called when ``route_with_llm`` is set and the
    rules did not understand the question (intent classification, validated before use)."""
    t0 = time.perf_counter()
    if use_llm:
        # A new question supersedes the narration of the previous answer: stop it now so the CPU-bound
        # local model does not slow down this deterministic answer.
        narration.new_generation()
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
                    "Execute um forecast primeiro – o analista só explica resultados calculados.",
                ),
            },
            None,
            "none",
            t0,
            understood=False,
            narration=_narration(use_llm, "no_run"),
        )
    members = _members(ctx)
    intent = parse(question, members, list(ctx.future_dates), ctx.last_actual)
    routing: dict[str, Any] | None = None
    if intent is None and not route_with_llm:
        clarification = _clarify(question, lang, members)
        if clarification:
            return _wrap(
                ctx,
                question,
                lang,
                clarification,
                None,
                "none",
                t0,
                understood=False,
                narration=_narration(use_llm, "not_understood"),
            )
    if intent is None and route_with_llm and use_llm:
        intent, routing = _route_with_llm(ctx, question, lang, members)
    if intent is None:
        interpretable = False
        if use_llm and not route_with_llm:
            interpretable = bool(llm.status(max_wait=0.6).get("available"))
        # "nem com a ajuda da IA local" only when the model actually answered (or ran out of time).
        llm_tried = bool(routing) and routing.get("status") in ("unknown", "timeout", "error")
        return _wrap(
            ctx,
            question,
            lang,
            _not_understood(question, lang, llm_tried=llm_tried),
            None,
            "none",
            t0,
            understood=False,
            interpretable=interpretable,
            narration=_narration(use_llm, "not_understood"),
            routing=routing,
        )

    # Page-level filters complement entities found in the question.
    for k, v in (filters or {}).items():
        if v and k not in intent.filters:
            intent.filters[k] = v
    result = HANDLERS[intent.name](ctx, intent)
    return _wrap(
        ctx,
        question,
        intent.language,
        result,
        intent,
        "rule-based NLG",
        t0,
        understood=True,
        narration=_narration(use_llm, intent=intent.name),
        routing=routing,
        facts=narration.compact_facts(result, intent.language),
    )


def _wrap(
    ctx: PlanningContext,
    question: str,
    lang: str,
    result: dict[str, Any],
    intent: Intent | None,
    engine: str,
    t0: float,
    grounding: dict[str, Any] | None = None,
    *,
    understood: bool = True,
    interpretable: bool = False,
    narration: dict[str, Any] | None = None,
    routing: dict[str, Any] | None = None,
    facts: dict[str, Any] | None = None,
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
    base["understood"] = understood
    base["interpretable"] = interpretable
    base["narration"] = narration or {"available": False, "model": None, "reason": None}
    # Compact facts for /api/ai/narrate: formatted indicators + the numbers written in the draft.
    base["facts"] = facts or {}
    base["meta"] = {
        "question": question,
        "language": lang,
        "intent": intent.as_dict() if intent else None,
        "engine": engine,
        "grounding": grounding or {"checked": False},
        "query": result.get("query"),
        "run_id": ctx.run_id,
        "dataset_version": ctx.version,
        "routing": routing,
        "latency_ms": round((time.perf_counter() - t0) * 1000),
    }
    return clean(base)
