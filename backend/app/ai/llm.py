"""Local LLM (Ollama) client + numeric grounding guard.

The LLM only rewrites explanations of results that were already computed.
``grounding_violations`` rejects any answer containing a number that cannot
be traced to the structured facts - the deterministic answer is used instead.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from app.config import settings

_status_cache: dict[str, Any] = {"t": 0.0, "value": None}

SYSTEM_PROMPT = """You are the ForecastLab AI Demand Analyst, a senior demand planning and S&OP expert.
You explain results that were computed by statistical engines. STRICT RULES:
1. Use ONLY numbers that appear in FACTS or DRAFT. Never invent, estimate or recompute numbers.
2. Do not add new metrics, months, customers or products that are not in FACTS.
3. Be concise and executive: 2-4 sentences for "answer", up to 3 short insights, up to 2 recommendations.
4. Answer in {language}.
5. Return JSON: {{"answer": str, "insights": [str], "recommendations": [str]}}."""

INTENT_PROMPT = """Classify the user's demand-planning question into exactly one intent.
Intents: {intents}
Return JSON: {{"intent": one of the intent names or "unknown", "dimension": one of
["sku","customer","region","channel","category","brand", null], "direction": one of ["over","under","best","worst", null]}}"""


def status(force: bool = False) -> dict[str, Any]:
    """Is Ollama reachable and is the configured model pulled? (cached 30 s)"""
    now = time.time()
    if not force and _status_cache["value"] is not None and now - _status_cache["t"] < 30:
        return _status_cache["value"]
    value: dict[str, Any] = {
        "enabled": settings.ai_enabled,
        "url": settings.ollama_url,
        "model": settings.ollama_model,
        "available": False,
        "models": [],
    }
    if settings.ai_enabled:
        try:
            r = httpx.get(f"{settings.ollama_url}/api/tags", timeout=2.0)
            r.raise_for_status()
            models = [m.get("name", "") for m in r.json().get("models", [])]
            value["models"] = models
            base = settings.ollama_model.split(":")[0]
            value["available"] = any(m == settings.ollama_model or m.split(":")[0] == base for m in models)
            if not value["available"]:
                value["reason"] = f"Model '{settings.ollama_model}' not pulled (ollama pull {settings.ollama_model})"
        except Exception as exc:
            value["reason"] = f"Ollama not reachable at {settings.ollama_url} ({type(exc).__name__})"
    else:
        value["reason"] = "AI disabled (FORECASTLAB_AI_ENABLED=false)"
    _status_cache.update(t=now, value=value)
    return value


def _chat(messages: list[dict[str, str]], schema: dict[str, Any] | None = None) -> str:
    payload: dict[str, Any] = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.1, "num_ctx": 4096},
        "format": schema or "json",
    }
    r = httpx.post(f"{settings.ollama_url}/api/chat", json=payload, timeout=settings.ollama_timeout_s)
    r.raise_for_status()
    return r.json()["message"]["content"]


EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "insights": {"type": "array", "items": {"type": "string"}},
        "recommendations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "insights", "recommendations"],
}


def explain(question: str, facts: dict[str, Any], draft: dict[str, Any], language: str) -> dict[str, Any]:
    lang = "Brazilian Portuguese" if language == "pt" else "English"
    content = (
        f"QUESTION: {question}\n\nFACTS (computed by ForecastLab engines, JSON):\n"
        f"{json.dumps(facts, default=str)[:6000]}\n\nDRAFT ANSWER (correct numbers):\n"
        f"{json.dumps({k: draft.get(k) for k in ('answer', 'insights', 'recommendations')}, ensure_ascii=False)}\n\n"
        "Rewrite the draft as a clear executive explanation following the rules."
    )
    raw = _chat(
        [{"role": "system", "content": SYSTEM_PROMPT.format(language=lang)}, {"role": "user", "content": content}],
        EXPLAIN_SCHEMA,
    )
    data = json.loads(raw)
    return {
        "answer": str(data.get("answer", "")).strip(),
        "insights": [str(x) for x in data.get("insights", [])][:4],
        "recommendations": [str(x) for x in data.get("recommendations", [])][:3],
    }


def classify_intent(question: str, intents: dict[str, str]) -> dict[str, Any]:
    raw = _chat(
        [
            {"role": "system", "content": INTENT_PROMPT.format(intents=json.dumps(intents))},
            {"role": "user", "content": question},
        ]
    )
    return json.loads(raw)


# ------------------------------------------------------------------------------- grounding
_NUM = re.compile(r"(?<![\w.])[-+]?\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?")


def _collect(obj: Any, out: list[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, int | float):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect(v, out)
    elif isinstance(obj, list | tuple):
        for v in obj:
            _collect(v, out)
    elif isinstance(obj, str):
        for m in _NUM.finditer(obj):
            v = _parse_number(m.group(0))
            if v is not None:
                out.append(v)


def _parse_number(tok: str) -> float | None:
    s = tok.strip().replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        s = s.replace(",", "") if len(parts[-1]) == 3 and len(parts) > 1 else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def allowed_numbers(*sources: Any) -> list[float]:
    raw: list[float] = []
    for s in sources:
        _collect(s, raw)
    allowed: set[float] = set()
    for v in raw:
        for k in (v, v * 100, v / 1e3, v / 1e6, v / 1e9, abs(v), abs(v) * 100, abs(v) / 1e3, abs(v) / 1e6):
            allowed.add(round(k, 6))
    return sorted(allowed)


def grounding_violations(text: str, allowed: list[float]) -> list[str]:
    """Numbers in ``text`` that do not match any allowed value (1.5% / 0.06 tolerance)."""
    bad = []
    for m in _NUM.finditer(text):
        v = _parse_number(m.group(0))
        if v is None:
            continue
        v = abs(v)
        if v <= 31 and float(v).is_integer():  # day/month counts, top-N, small integers
            continue
        if 1900 <= v <= 2100 and float(v).is_integer():  # years
            continue
        if not any(abs(v - a) <= max(0.06, 0.015 * abs(a)) for a in allowed):
            bad.append(m.group(0))
    return bad
