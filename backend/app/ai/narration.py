"""Background narration: the local LLM rewrites an answer that was already computed.

``/api/ai/ask`` returns the deterministic answer at once together with ``compact_facts`` (the
formatted indicators plus every number written in the draft, at most ``FACTS_MAX_CHARS``). The page
then calls ``/api/ai/narrate`` with that draft; ``narrate`` asks the local model for a short
executive version of the answer (two sentences) and accepts it only when it passes every guard:

* numeric grounding - every number can be traced to the facts or the draft (``llm.grounding_violations``);
* verdict - classification words (DESAFIADORA, superestimado...) are the computed ones;
* direction - "queda"/"cai" never sits next to a positive change, "cresce"/"acima" never next to a
  negative one;
* added value - a near-copy of the computed answer is not presented as a refinement.

Insights and recommendations stay the computed ones: measured on qwen3:1.7b, free-form insights were
where a small model misread directions (e.g. "redução de receita" for a +2,7% revenue scenario), and
on a CPU every extra sentence costs ~10 s. Otherwise the computed version stays on screen.

Only one narration runs at a time: a newer question, narration or intent classification cancels the
older one ("latest wins"), which frees the single CPU-bound Ollama worker for the question the user
is looking at.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Any

from . import llm
from .intents import detect_language
from .nlg import money, num, pct, units

log = logging.getLogger("forecastlab.ai")

FACTS_MAX_CHARS = 1800
NARRATE_OPTIONS = {"temperature": 0.1, "num_ctx": 2048, "num_predict": 320}
DRAFT_ANSWER_MAX = 900
DRAFT_ITEM_MAX = 300
DRAFT_INSIGHTS_MAX = 4
DRAFT_RECS_MAX = 3
ANSWER_MAX_CHARS = 360  # two short sentences (~90 tokens: ~10-20 s on a CPU)
COPY_RATIO = 0.9  # SequenceMatcher ratio above which the rewrite is a copy of the computed answer

# Answers worth an executive rewrite. Rankings and lists (risks, bias / accuracy rankings, budget gaps
# by customer, FVA, models, demand patterns) are already the clearest form, and a small model tends to
# attach their numbers to the wrong customer or SKU. What-if simulations are not narrated either: the
# lever and the outcome carry opposite signs ("preço -5,0%" -> "receita +2,9%"), and qwen3:1.7b wrote
# "a receita do cenário cai -5,0%" - every number grounded, the meaning wrong.
NARRATABLE_INTENTS = frozenset(
    {
        "summary",
        "forecast_value",
        "target_feasibility",
        "metric_lookup",
        "entity_overview",
        "forecast_drivers",
    }
)

# Hierarchy codes in the scope line given to the model, in pt-BR ("cliente: Litoral Market").
_DIM_PT = {
    "region": "região",
    "channel": "canal",
    "customer": "cliente",
    "category": "categoria",
    "brand": "marca",
    "sku": "SKU",
    "product": "produto",
}

NARRATE_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string", "maxLength": ANSWER_MAX_CHARS}},
    "required": ["answer"],
}
SYSTEM_PROMPT = {
    "pt": """Você é o Analista de Demanda do ForecastLab, especialista em S&OP. Você recebe a RESPOSTA
CALCULADA a uma pergunta e escreve a versão executiva para um diretor comercial, em português do Brasil.
REGRAS:
1. "answer": exatamente 2 frases curtas. A 1ª dá a conclusão com os 1 ou 2 números principais; a 2ª
   diz o que isso significa para o negócio. Não copie a resposta calculada.
2. Copie cada número exatamente como está na RESPOSTA CALCULADA (ex.: "R$ 9,83 mi", "14,8%") e
   mantenha-o junto do mesmo indicador, cliente ou produto. Nunca calcule, arredonde nem invente números.
3. Mantenha a classificação calculada (ex.: DESAFIADORA) e o sentido de cada variação: número negativo
   é queda ou "abaixo"; número positivo é alta ou "acima".
4. Não cite clientes, produtos, meses ou métricas que não apareçam na RESPOSTA CALCULADA ou nos FATOS.
5. Responda apenas com o JSON pedido.
EXEMPLO
RESPOSTA CALCULADA: A meta do 1º trimestre (região X) é AGRESSIVA: meta de R$ 30,00 mi vs consenso de
R$ 24,50 mi. Probabilidade de atingir: 8%. Exige +25,0% vs ano anterior, enquanto o forecast indica +4,1%.
{"answer": "A meta do 1º trimestre é AGRESSIVA: pede R$ 30,00 mi, mas o consenso indica R$ 24,50 mi e a
chance de atingi-la é de 8%. Sem novas ações comerciais, o plano dificilmente fecha essa diferença."}""",
    "en": """You are the ForecastLab Demand Analyst, an S&OP expert. You receive the COMPUTED ANSWER
to a question and write the executive version for a sales director, in English. RULES:
1. "answer": exactly 2 short sentences. The 1st gives the conclusion with the 1 or 2 main numbers;
   the 2nd says what it means for the business. Do not copy the computed answer.
2. Copy every number exactly as in the COMPUTED ANSWER and keep it next to the same metric, customer
   or product. Never compute, round or invent numbers.
3. Keep the computed classification and the direction of every change: a negative number is a drop or
   "below"; a positive number is a rise or "above".
4. Do not mention customers, products, months or metrics that are not in the COMPUTED ANSWER or FACTS.
5. Reply with the requested JSON only.""",
}

# ------------------------------------------------------------------------------ latest wins
_gen_lock = threading.Lock()
_generation = 0


def new_generation() -> int:
    """Start a new foreground job; every older narration is cancelled (watchdog in ``llm.chat``)."""
    global _generation
    with _gen_lock:
        _generation += 1
        return _generation


def is_stale(gen: int) -> bool:
    with _gen_lock:
        return gen != _generation


# ------------------------------------------------------------------------------ compact facts
# A number as written in a pt-BR/en draft, with its currency, sign and unit:
# "R$ 94,30 mi", "-R$ 2,00 mi", "+7,3%", "12,5 p.p.", "8,46 mi unidades", "29%".
_DRAFT_NUM = re.compile(
    r"(?<![\w/-])(?:[-+−]?R\$\s?)?[-+−]?\d(?:[\d.,]*\d)?"
    r"(?:\s?(?:%|p\.p\.|pp\b|bi\b|mi\b|mil\b|M\b|K\b|B\b)|(?!\w))"  # "200ml" is a product, not a number
    r"(?:\s(?:de\s)?(?:unidades|units|meses|séries|series|SKUs|clientes|alertas)\b)?"
)
_SMALL_INT = re.compile(r"^\d{1,2}$")


def _fmt(value: Any, fmt: str | None, lang: str) -> str:
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, int | float):
        if fmt == "currency":
            return money(value, lang)
        if fmt == "units":
            return units(value, lang)
        if fmt == "percent":
            return pct(value, lang)
        if fmt == "percent_signed":
            return pct(value, lang, signed=True)
        return num(value, lang, 0 if float(value).is_integer() else 2)
    return str(value)


def _draft_numbers(*texts: str) -> list[str]:
    seen: list[str] = []
    for text in texts:
        for m in _DRAFT_NUM.finditer(text or ""):
            tok = m.group(0).strip()
            if not tok.endswith("p.p."):
                tok = tok.rstrip(".,")
            if _SMALL_INT.match(tok):
                continue  # counts like "(0 críticos, 1 alto)" are always accepted by the guard
            if tok and any(ch.isdigit() for ch in tok) and tok not in seen:
                seen.append(tok)
    return seen


def _fit(facts: dict[str, Any], limit: int = FACTS_MAX_CHARS) -> dict[str, Any]:
    """Drop trailing items until the JSON fits ``limit`` characters."""

    def size(d: dict[str, Any]) -> int:
        return len(json.dumps(d, ensure_ascii=False, default=str))

    out = json.loads(json.dumps(facts, ensure_ascii=False, default=str))
    keys = list(out)
    while size(out) > limit and keys:
        key = keys[-1]
        v = out[key]
        if isinstance(v, list) and len(v) > 1:
            out[key] = v[:-1]
        elif isinstance(v, dict) and len(v) > 1:
            out[key] = dict(list(v.items())[:-1])
        elif isinstance(v, str) and len(v) > 80:
            out[key] = v[: max(80, len(v) - 200)]
        else:
            out.pop(key)
            keys.pop()
    return out


def compact_facts(result: dict[str, Any], lang: str = "pt", filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """The facts the LLM may use: formatted indicators + every number written in the draft (≤ 1.800 chars)."""
    out: dict[str, Any] = {}
    scope = _scope_text(filters or result.get("filters"), lang)
    if scope:
        out["escopo"] = scope
    metrics = {}
    for m in result.get("metrics") or []:
        label = str(m.get("label") or "").strip()
        if label and m.get("value") is not None:
            metrics[label] = _fmt(m.get("value"), m.get("format"), lang)
    if metrics:
        out["indicadores"] = metrics
    nums = _draft_numbers(
        result.get("answer") or "", *(result.get("insights") or []), *(result.get("recommendations") or [])
    )
    if nums:
        out["numeros_do_rascunho"] = nums
    return _fit(out)


def _sanitize_facts(facts: Any) -> dict[str, Any]:
    """Facts sent back by the page: keep a dict, cap its size (raw handler facts are compacted too)."""
    if isinstance(facts, dict):
        return _fit(facts)
    if isinstance(facts, list):
        return _fit({"fatos": facts})
    return {}


# ------------------------------------------------------------------------------ output parsing
_STR = r'"((?:[^"\\]|\\.)*)"'


def _unescape(s: str) -> str:
    try:
        return json.loads(f'"{s}"')
    except json.JSONDecodeError:
        return s


def parse_rewrite(raw: str) -> dict[str, Any] | None:
    """Parse the model's JSON; when ``num_predict`` cut it short, salvage the complete strings."""
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S).strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {
                "answer": str(data.get("answer") or "").strip(),
                "insights": [str(x).strip() for x in (data.get("insights") or []) if str(x).strip()],
                "complete": True,
            }
    except json.JSONDecodeError:
        pass
    m = re.search(r'"answer"\s*:\s*' + _STR, raw)
    if m:
        return {"answer": _unescape(m.group(1)).strip(), "insights": [], "complete": False}
    m = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)$', raw, flags=re.S)  # string cut by num_predict
    if m:
        return {"answer": _tidy(_unescape(m.group(1)), 0), "insights": [], "complete": False}
    return None


_SENTENCE_END = re.compile(r"[.!?…)](?=\s|$)")


def _tidy(text: str, limit: int) -> str:
    """A string cut by the schema's ``maxLength`` (or ``num_predict``) ends at its last complete sentence."""
    text = " ".join(text.split())
    if (limit and len(text) < limit - 5) or text.endswith((".", "!", "?", "…", ")")):
        return text
    ends = [m.end() for m in _SENTENCE_END.finditer(text)]
    if ends and ends[-1] >= min(40, len(text) // 3):
        return text[: ends[-1]]
    return text.rstrip(" ,;:-") + "…"


# ------------------------------------------------------------------------------ guards
# Classification words must not change between the computed answer and the rewrite: a small model
# reading "A meta é realista?" may answer "a meta é realista" although the engine classed it as
# DESAFIADORA. Every verdict stem in the rewrite must already appear in the computed answer or facts.
_VERDICT = re.compile(
    r"\b(realist\w*|desafiador\w*|agressiv\w*|superestim\w*|subestim\w*|equilibrad\w*|inviáve\w*|viáve\w*"
    r"|realistic\w*|stretch\w*|aggressive\w*|overforecast\w*|underforecast\w*|feasible|infeasible)",
    re.IGNORECASE,
)


def verdict_violations(text: str, *sources: Any) -> list[str]:
    src = " ".join(json.dumps(x, ensure_ascii=False) if not isinstance(x, str) else x for x in sources).lower()
    bad: list[str] = []
    for m in _VERDICT.finditer(text or ""):
        word = m.group(1)
        if word.lower()[:7] not in src and word not in bad:
            bad.append(word)
    return bad


_DOWN = re.compile(
    r"\b(ca[ií](?:r|u|a|ndo|rá|rão|ram|em)?|queda\w*|redu[zçc]\w*|diminu\w*|recu[oa]\w*|recuou|encolh\w*"
    r"|retra[çc]\w*|abaixo|perd\w*|pior\w*|drop\w*|fall\w*|fell|declin\w*|decreas\w*|below|lower)\b",
    re.IGNORECASE,
)
_UP = re.compile(
    r"\b(cresc\w*|aument\w*|alta|sobe|sobem|subi\w*|elev\w*|acima|ganh\w*|expan\w*|avan[çc]\w*"
    r"|rise|rises|rising|rose|grow\w*|increas\w*|above|higher|gain\w*)\b",
    re.IGNORECASE,
)
_PCT = re.compile(r"(?<![\w.,])([-+−]?)(\d+(?:[.,]\d+)?)\s?%")
_CLAUSE = re.compile(r"[.;:!?]\s|,\s|\s(?:e|mas|enquanto|and|but|while)\s")


def _signs_in(source: str) -> dict[str, set[int]]:
    signs: dict[str, set[int]] = {}
    for m in _PCT.finditer(source):
        mag = m.group(2).replace(",", ".")
        signs.setdefault(mag, set()).add(-1 if m.group(1) in ("-", "−") else 1)
    return signs


def direction_violations(text: str, source: str) -> list[str]:
    """Clauses where a "down" word sits next to a positive change (or an "up" word next to a negative one).

    Unsigned percentages take their sign from the computed answer when it is unambiguous there.
    """
    known = _signs_in(source)
    bad: list[str] = []
    for clause in _CLAUSE.split(text or ""):
        down, up = bool(_DOWN.search(clause)), bool(_UP.search(clause))
        if down == up:
            continue  # no direction word, or both: nothing to check
        for m in _PCT.finditer(clause):
            if m.group(1):
                sign = -1 if m.group(1) in ("-", "−") else 1
            else:
                candidates = known.get(m.group(2).replace(",", "."), set())
                if len(candidates) != 1:
                    continue
                sign = next(iter(candidates))
            if (down and sign > 0) or (up and sign < 0):
                bad.append(clause.strip()[:80])
                break
    return bad + reference_violations(text, source)


# "acima/abaixo do orçamento / da meta" must agree with the computed gap ("-1,8% vs orçamento",
# "Orçamento: R$ 8,31 mi (-1,8%)").
_REF_WORD = {"orçamento": "budget", "budget": "budget", "meta": "target", "target": "target"}
_REF_CLAIM = re.compile(
    r"\b(acima|abaixo|above|below)\s+(?:d[oa]s?\s+|of\s+(?:the\s+)?|the\s+)?(orçamento|meta|budget|target)"
    r"(?:\s+(?:e|and)\s+(?:d[oa]s?\s+|the\s+)?(orçamento|meta|budget|target))?",
    re.IGNORECASE,
)
_REF_SIGNED = (
    re.compile(
        r"([-+−])\d+(?:[.,]\d+)?\s?%\s+(?:vs\.?|versus|contra)\s+(?:o\s+|a\s+|the\s+)?(orçamento|meta|budget|target)",
        re.I,
    ),
    re.compile(r"(orçamento|meta|budget|target)\s*:?\s*(?:R\$\s?[\d.,]+\s?(?:bi|mi|mil|M|K|B)?\s*)?\(([-+−])\d", re.I),
)


def reference_violations(text: str, source: str) -> list[str]:
    signs: dict[str, set[int]] = {}
    for m in _REF_SIGNED[0].finditer(source):
        signs.setdefault(_REF_WORD[m.group(2).lower()], set()).add(-1 if m.group(1) in ("-", "−") else 1)
    for m in _REF_SIGNED[1].finditer(source):
        signs.setdefault(_REF_WORD[m.group(1).lower()], set()).add(-1 if m.group(2) in ("-", "−") else 1)
    bad: list[str] = []
    for m in _REF_CLAIM.finditer(text or ""):
        claim = -1 if m.group(1).lower() in ("abaixo", "below") else 1
        for ref in filter(None, (m.group(2), m.group(3))):
            known = signs.get(_REF_WORD[ref.lower()], set())
            if len(known) == 1 and next(iter(known)) != claim:
                bad.append(m.group(0))
                break
    return bad


# ------------------------------------------------------------------------------ narrate
def _draft(answer: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": str(answer.get("answer") or "")[:DRAFT_ANSWER_MAX],
        "insights": [str(x)[:DRAFT_ITEM_MAX] for x in (answer.get("insights") or [])][:DRAFT_INSIGHTS_MAX],
        "recommendations": [str(x)[:DRAFT_ITEM_MAX] for x in (answer.get("recommendations") or [])][:DRAFT_RECS_MAX],
    }


def _scope_text(filters: dict[str, Any] | None, lang: str = "pt") -> str:
    """Scope line such as ``cliente: Litoral Market, região: Sul`` (pt-BR dimension names for a pt-BR prompt)."""
    items = [
        f"{_DIM_PT.get(k, k) if lang == 'pt' else k}: {v}"
        for k, v in (filters or {}).items()
        if isinstance(v, str | int | float) and not isinstance(v, bool) and v
    ]
    return ", ".join(items)


def narrate(
    question: str,
    lang: str,
    filters: dict[str, Any] | None,
    answer: dict[str, Any],
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Executive rewrite of a computed answer by the local LLM.

    Returns ``{status: "ok", answer, insights, recommendations, model, elapsed_s, grounding}`` (insights
    and recommendations are the computed ones) or ``{status: "rejected" | "timeout" | "unavailable" |
    "cancelled", reason (pt-BR), model, elapsed_s}``.
    """
    t0 = time.perf_counter()
    lang = "en" if lang == "en" else "pt"
    gen = new_generation()

    def cancelled() -> bool:
        return is_stale(gen) or (should_cancel is not None and should_cancel())

    def out(status: str, reason: str | None = None, model: str | None = None, **kw: Any) -> dict[str, Any]:
        return {
            "status": status,
            "reason": reason,
            "model": model,
            "elapsed_s": round(time.perf_counter() - t0, 1),
            **kw,
        }

    draft = _draft(answer or {})
    if not draft["answer"].strip():
        return out("rejected", "Não há resposta calculada para refinar.")
    st = llm.status(max_wait=3.0)
    if not st.get("available"):
        return out("unavailable", st.get("reason") or "A IA local não está disponível.")
    model = st["model"]
    facts = _sanitize_facts((answer or {}).get("facts"))
    scope = _scope_text(filters, lang)
    labels = (
        {"q": "PERGUNTA", "s": "ESCOPO", "f": "FATOS", "d": "RESPOSTA CALCULADA"}
        if lang == "pt"
        else {"q": "QUESTION", "s": "SCOPE", "f": "FACTS", "d": "COMPUTED ANSWER"}
    )
    content = "\n".join(
        x
        for x in (
            f"{labels['q']}: {question[:300]}",
            f"{labels['s']}: {scope}" if scope else "",
            f"{labels['f']}: {json.dumps(facts, ensure_ascii=False)}",
            f"{labels['d']}: {draft['answer']}",
        )
        if x
    )
    try:
        raw = llm.chat(
            [{"role": "system", "content": SYSTEM_PROMPT[lang]}, {"role": "user", "content": content}],
            NARRATE_SCHEMA,
            model=model,
            options=NARRATE_OPTIONS,
            timeout=llm.settings.ollama_timeout_s,
            should_cancel=cancelled,
        )
    except llm.LLMCancelled:
        return out("cancelled", "Refinamento interrompido por uma nova pergunta.", model)
    except llm.LLMTimeout:
        secs = round(llm.settings.ollama_timeout_s)
        return out("timeout", f"A IA local não terminou em {secs} s; mantida a versão calculada.", model)
    except llm.LLMUnavailable:
        return out("unavailable", "A IA local ficou indisponível durante o refinamento.", model)
    except llm.LLMError as exc:  # raw Ollama errors are English and technical: log them, show pt-BR
        log.warning("Narration by %s failed: %s", model, exc)
        return out("rejected", "A IA local falhou ao refinar o texto; mantida a versão calculada.", model)

    parsed = parse_rewrite(raw)
    text = _tidy(parsed["answer"], ANSWER_MAX_CHARS) if parsed else ""
    if len(text) < 20:
        return out("rejected", "A IA local devolveu um texto incompleto; mantida a versão calculada.", model)
    if lang == "pt" and detect_language(text) == "en":
        return out("rejected", "A IA local respondeu em outro idioma; mantida a versão calculada.", model)
    if difflib.SequenceMatcher(None, text, draft["answer"]).ratio() >= COPY_RATIO:
        return out("rejected", "A versão da IA local repetia a resposta calculada; mantida a versão calculada.", model)
    sources = (draft["answer"], draft["insights"], draft["recommendations"], facts)
    changed = verdict_violations(text, *sources)
    if changed:
        return out(
            "rejected",
            f"A IA local mudou a classificação calculada ({', '.join(changed[:3])}); mantida a versão calculada.",
            model,
            grounding={"checked": True, "passed": False, "violations": changed[:10]},
        )
    flipped = direction_violations(text, " ".join([draft["answer"], *draft["insights"], *draft["recommendations"]]))
    if flipped:
        return out(
            "rejected",
            "A IA local inverteu o sentido de uma variação (alta × queda); mantida a versão calculada.",
            model,
            grounding={"checked": True, "passed": False, "violations": flipped[:10]},
        )
    allowed = llm.allowed_numbers(facts, *sources[:3], question, filters or {})
    bad = llm.grounding_violations(text, allowed)
    if bad:
        shown = ", ".join(bad[:3])
        return out(
            "rejected",
            f"A IA local citou números sem lastro nos fatos calculados ({shown}); mantida a versão calculada.",
            model,
            grounding={"checked": True, "passed": False, "violations": bad[:10]},
        )
    return out(
        "ok",
        None,
        model,
        answer=text,
        insights=draft["insights"],
        recommendations=draft["recommendations"],
        grounding={"checked": True, "passed": True, "violations": []},
        complete=bool(parsed and parsed["complete"]),
    )
