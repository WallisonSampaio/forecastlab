"""Local LLM (Ollama) client + numeric grounding guard.

The LLM never computes a number and ``/api/ai/ask`` never waits for it:

* ``status`` reports whether Ollama is reachable and which pulled model is used. The check runs in a
  background thread and is cached, so callers on the request path only wait a bounded time
  (``max_wait``). The first successful check also starts a one-off warm-up thread that loads the
  model into memory (``keep_alive``).
* ``chat`` streams one completion with ``think: false``, a JSON-schema output, a hard deadline and
  cooperative cancellation (a newer request or a closed browser tab stops the generation, which frees
  the single CPU-bound Ollama worker).
* ``classify_intent`` maps a question the rules did not understand to an intent (strict schema; the
  caller validates the result against the known intents and entities).
* ``grounding_violations`` rejects any text containing a number that cannot be traced to the facts.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger("forecastlab.ai")

# Preferred local models, fastest first (CPU-only machines: qwen3:1.7b rewrites a short answer in ~20 s).
PREFERRED_MODELS = ("qwen3:1.7b", "llama3.2:3b", "qwen3:4b-instruct-2507-q4_K_M", "qwen3:4b")
KEEP_ALIVE = "30m"
STATUS_TTL_OK = 30.0  # seconds a positive check is reused
STATUS_TTL_FAIL = 10.0  # seconds a negative check is reused
TAGS_TIMEOUT = 3.0  # /api/tags can take ~1,5 s while the CPU is busy generating
WARMUP_TIMEOUT = 300.0
CLASSIFY_TIMEOUT = 45.0
CLASSIFY_NUM_PREDICT = 120

CHECKING_REASON = "Verificando a IA local…"


class LLMError(Exception):
    """The local LLM failed (HTTP error, invalid output...)."""


class LLMTimeout(LLMError):
    """No complete answer before the deadline."""


class LLMCancelled(LLMError):
    """A newer request (or a closed browser tab) cancelled this generation."""


class LLMUnavailable(LLMError):
    """Ollama is disabled, unreachable or has no usable model."""


# ------------------------------------------------------------------------------ HTTP layer
def _client(timeout: float | httpx.Timeout) -> httpx.Client:
    """Every call to Ollama goes through this factory (tests replace it with a mock transport)."""
    return httpx.Client(base_url=settings.ollama_url, timeout=timeout)


def _fetch_models() -> list[str]:
    with _client(TAGS_TIMEOUT) as c:
        r = c.get("/api/tags")
        r.raise_for_status()
        return [m.get("name", "") for m in r.json().get("models", []) if m.get("name")]


# ------------------------------------------------------------------------------ model choice
def _match(name: str, models: list[str]) -> str | None:
    if name in models:
        return name
    if ":" not in name and f"{name}:latest" in models:
        return f"{name}:latest"
    return None


def select_model(models: list[str], configured: str | None = None) -> tuple[str | None, str | None]:
    """(model, note). ``OLLAMA_MODEL`` when set AND pulled; else the first pulled preferred model;
    else any pulled chat model. ``note`` (pt-BR) explains a configured model that is not pulled."""
    note = None
    if configured:
        hit = _match(configured, models)
        if hit:
            return hit, None
        note = f"O modelo definido em OLLAMA_MODEL ('{configured}') não está baixado; usando outro modelo local."
    for name in PREFERRED_MODELS:
        if name in models:
            return name, note
    chat_models = [m for m in models if "embed" not in m.lower()]
    return (chat_models[0] if chat_models else None), note


# ------------------------------------------------------------------------------ status + warm-up
_lock = threading.Lock()
_status: dict[str, Any] = {"t": 0.0, "value": None, "thread": None}
_warm: dict[str, Any] = {"model": None, "state": "idle", "elapsed_s": None}


def reset_state() -> None:
    """Forget the cached status and warm-up (tests, or after changing the Ollama setup)."""
    with _lock:
        _status.update(t=0.0, value=None, thread=None)
        _warm.update(model=None, state="idle", elapsed_s=None)


def _base_value() -> dict[str, Any]:
    return {
        "enabled": settings.ai_enabled,
        "url": settings.ollama_url,
        "configured_model": settings.ollama_model or None,
        "model": None,
        "models": [],
        "available": False,
        "reason": None,
        "note": None,
        "timeout_s": settings.ollama_timeout_s,
    }


def _check() -> dict[str, Any]:
    value = _base_value()
    try:
        models = _fetch_models()
    except httpx.TimeoutException:
        with _lock:
            previous = _status["value"]
        if previous and previous.get("available"):
            return dict(previous)  # Ollama is busy generating, not down: keep the last good answer
        value["reason"] = f"O Ollama não respondeu a tempo em {settings.ollama_url}."
        return value
    except Exception as exc:  # any failure means "not available"
        log.info("Ollama not reachable at %s: %s", settings.ollama_url, exc)
        value["reason"] = f"Ollama não encontrado em {settings.ollama_url}."
        return value
    value["models"] = models
    model, note = select_model(models, settings.ollama_model or None)
    value["model"] = model
    value["note"] = note
    value["available"] = model is not None
    if model is None:
        value["reason"] = "Nenhum modelo baixado no Ollama (ex.: ollama pull qwen3:1.7b)."
    return value


def _refresh() -> None:
    value = _check()
    with _lock:
        _status.update(t=time.monotonic(), value=value, thread=None)
    if value.get("available"):
        _ensure_warm(value["model"])


def _with_warm(value: dict[str, Any]) -> dict[str, Any]:
    out = dict(value)
    with _lock:
        if out.get("available") and _warm["model"] == out.get("model"):
            out["warmup"] = {"state": _warm["state"], "elapsed_s": _warm["elapsed_s"]}
        else:
            out["warmup"] = {"state": "idle", "elapsed_s": None}
    return out


def status(force: bool = False, max_wait: float = 3.0) -> dict[str, Any]:
    """Is Ollama reachable and which pulled model is used?

    Never blocks longer than ``max_wait`` seconds: a stale cached value is returned at once while a
    background thread refreshes it; without any value yet, the call waits up to ``max_wait`` and then
    answers "checking" (not available).
    """
    if not settings.ai_enabled:
        value = _base_value()
        value["reason"] = "IA local desativada (FORECASTLAB_AI_ENABLED=false)."
        return _with_warm(value)
    now = time.monotonic()
    with _lock:
        value = _status["value"]
        ttl = STATUS_TTL_OK if value and value.get("available") else STATUS_TTL_FAIL
        fresh = value is not None and now - _status["t"] < ttl
        thread = _status["thread"]
        if (force or not fresh) and thread is None:
            thread = threading.Thread(target=_refresh, name="ollama-status", daemon=True)
            _status["thread"] = thread
            thread.start()
    if fresh and not force:
        return _with_warm(value)
    if value is not None and not force:
        return _with_warm(value)  # stale: answer now, refresh in the background
    if thread is not None:
        thread.join(max_wait)
    with _lock:
        value = _status["value"]
    if value is None:
        value = _base_value()
        value.update(reason=CHECKING_REASON, checking=True)
    return _with_warm(value)


def _ensure_warm(model: str) -> None:
    """Load ``model`` into memory once per process (daemon thread; nobody waits for it)."""
    with _lock:
        if _warm["model"] == model and _warm["state"] in ("loading", "ready"):
            return
        _warm.update(model=model, state="loading", elapsed_s=None)
    threading.Thread(target=_warm_up, args=(model,), name="ollama-warmup", daemon=True).start()


def base_options() -> dict[str, Any]:
    """Options shared by every call (a different ``num_thread`` would force Ollama to reload the model)."""
    opts: dict[str, Any] = {"num_ctx": 2048}
    if settings.ollama_num_thread > 0:
        opts["num_thread"] = settings.ollama_num_thread
    return opts


def _warm_up(model: str) -> None:
    t0 = time.perf_counter()
    try:
        with _client(WARMUP_TIMEOUT) as c:
            # An empty prompt only loads the model; keep_alive keeps it resident between questions.
            body = {"model": model, "keep_alive": KEEP_ALIVE, "options": base_options()}
            r = c.post("/api/generate", json=body)
            r.raise_for_status()
        state = "ready"
    except Exception as exc:
        log.warning("Ollama warm-up of %s failed: %s", model, exc)
        state = "failed"
    with _lock:
        if _warm["model"] == model:
            _warm.update(state=state, elapsed_s=round(time.perf_counter() - t0, 1))


# ------------------------------------------------------------------------------ chat
def chat(
    messages: list[dict[str, str]],
    schema: dict[str, Any] | None = None,
    *,
    model: str,
    options: dict[str, Any] | None = None,
    timeout: float | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> str:
    """One streamed completion (``think: false``, JSON output). Returns the raw message content.

    Raises ``LLMTimeout`` after ``timeout`` seconds, ``LLMCancelled`` when ``should_cancel()`` turns
    true, ``LLMUnavailable`` on connection errors and ``LLMError`` on any other failure. A watchdog
    thread closes the connection as soon as the request is cancelled or late - even while Ollama is
    still reading the prompt - and Ollama then stops working on it.
    """
    timeout = float(timeout or settings.ollama_timeout_s)
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "think": False,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": 0.1, **base_options(), **(options or {})},
        "format": schema or "json",
    }
    deadline = time.monotonic() + timeout
    client = _client(httpx.Timeout(timeout, connect=3.0))
    finished = threading.Event()
    why: dict[str, str] = {}

    def watchdog() -> None:
        while not finished.wait(0.2):
            if should_cancel is not None and should_cancel():
                why["stop"] = "cancel"
            elif time.monotonic() > deadline:
                why["stop"] = "timeout"
            else:
                continue
            client.close()  # unblocks the reading thread
            return

    def stopped() -> LLMError | None:
        if why.get("stop") == "cancel" or (should_cancel is not None and should_cancel()):
            return LLMCancelled()
        if why.get("stop") == "timeout" or time.monotonic() > deadline:
            return LLMTimeout()
        return None

    threading.Thread(target=watchdog, name="ollama-watchdog", daemon=True).start()
    parts: list[str] = []
    done = False
    try:
        with client.stream("POST", "/api/chat", json=payload) as r:
            if r.status_code >= 400:
                r.read()
                raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
            for line in r.iter_lines():
                stop = stopped()
                if stop is not None:
                    raise stop
                if not line.strip():
                    continue
                data = json.loads(line)
                if data.get("error"):
                    raise LLMError(str(data["error"]))
                parts.append((data.get("message") or {}).get("content") or "")
                if data.get("done"):
                    done = True
                    break
    except LLMError:
        raise
    except httpx.TimeoutException as exc:
        raise LLMTimeout() from exc
    except json.JSONDecodeError as exc:
        raise LLMError("resposta inválida do Ollama") from exc
    except Exception as exc:  # the watchdog closed the socket, or the network failed
        stop = stopped()
        if stop is not None:
            raise stop from exc
        raise LLMUnavailable(type(exc).__name__) from exc
    finally:
        finished.set()
        client.close()
    if not done:
        stop = stopped()
        if stop is not None:
            raise stop
    return "".join(parts)


# ------------------------------------------------------------------------------ prompts
INTENT_HELP = {
    "summary": "resumo executivo; como estamos indo no geral; visão geral do plano",
    "forecast_value": "quanto vamos vender ou vendemos; previsão de vendas de um período ou entidade",
    "target_feasibility": "se a meta é realista ou será atingida",
    "metric_lookup": "valor de WMAPE, acurácia ou viés de uma entidade ou do total",
    "entity_overview": "situação de um cliente, região, canal, categoria, marca ou SKU citado",
    "what_if": "simulação: e se preço, distribuição, promoção ou marketing mudarem",
    "fva_overrides": "se os ajustes comerciais ajudaram ou pioraram o forecast (FVA)",
    "best_model": "qual modelo de forecast funciona melhor",
    "bias_ranking": "quem está superestimado ou subestimado (viés)",
    "worst_accuracy": "quem tem a pior ou a melhor acurácia; quem erra mais",
    "budget_gap": "onde estamos abaixo ou acima do orçamento",
    "forecast_drivers": "por que o forecast cresce ou cai; o que explica a previsão",
    "risks": "principais riscos e alertas; o que preocupa; o que olhar primeiro",
    "model_distribution": "quais modelos são campeões e com que frequência",
    "series_types": "padrões de demanda das séries (sazonal, intermitente...)",
}
DIMENSIONS = ("sku", "customer", "region", "channel", "category", "brand")
DIRECTIONS = ("over", "under", "abs", "best", "worst")
METRICS = ("wmape", "accuracy", "bias", "rmse", "mae")

INTENT_PROMPT = """Classifique a pergunta de planejamento de demanda em UMA intenção:
{intents}
Use "unknown" só quando a pergunta não tiver relação com vendas, clientes, produtos, metas ou forecast
(ex.: saudações).
"dimension": a dimensão pedida em rankings (sku, customer, region, channel, category, brand) ou "none".
"direction": over (superestimado), under (subestimado), abs (maior viés em módulo), best, worst ou "none".
"metric": wmape, accuracy, bias, rmse, mae ou "none".
"entities": trechos da pergunta que citam clientes, produtos, marcas, regiões, canais ou categorias.
"months": trechos da pergunta que citam meses ou períodos. Responda apenas com o JSON."""


def intent_schema(intents: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": [*intents, "unknown"]},
            "dimension": {"type": "string", "enum": [*DIMENSIONS, "none"]},
            "direction": {"type": "string", "enum": [*DIRECTIONS, "none"]},
            "metric": {"type": "string", "enum": [*METRICS, "none"]},
            "entities": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
            "months": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        },
        "required": ["intent", "dimension", "direction", "metric", "entities", "months"],
    }


def classify_intent(
    question: str,
    intents: dict[str, str] | list[str],
    *,
    model: str | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Raw LLM classification (strict schema). The caller MUST validate every field."""
    names = list(intents)
    if model is None:
        st = status(max_wait=3.0)
        if not st.get("available"):
            raise LLMUnavailable(st.get("reason") or "IA local indisponível")
        model = st["model"]
    lines = "\n".join(f"- {n}: {INTENT_HELP.get(n, '')}" for n in names)
    raw = chat(
        [
            {"role": "system", "content": INTENT_PROMPT.format(intents=lines)},
            {"role": "user", "content": question[:300]},
        ],
        intent_schema(names),
        model=model,
        options={"temperature": 0.0, "num_predict": CLASSIFY_NUM_PREDICT},
        timeout=CLASSIFY_TIMEOUT,
        should_cancel=should_cancel,
    )
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise LLMError("classificação inválida")
    return data


def explain(question: str, facts: dict[str, Any], draft: dict[str, Any], language: str) -> dict[str, Any]:
    """Backward-compatible synchronous rewrite (nothing on the request path uses it any more).

    Prompts and output schema live in ``app.ai.narration`` (``SYSTEM_PROMPT``, ``NARRATE_SCHEMA``).
    """
    from .narration import narrate

    out = narrate(question, language, {}, {**draft, "facts": facts})
    if out.get("status") != "ok":
        raise LLMError(out.get("reason") or out.get("status"))
    return {k: out[k] for k in ("answer", "insights", "recommendations")}


# ------------------------------------------------------------------------------- grounding
# A number: grouped thousands ("1.234.567", "1,234,567") with optional decimals, or a plain number
# ("9,83", "14.8", "2026"). Tokens glued to letters ("P90", "T1", "SKU20102", "FPS50") are identifiers.
_NUM = re.compile(r"(?<![\w.,])[-+]?(?:\d{1,3}(?:[.,]\d{3})+(?![\d])(?:[.,]\d+)?|\d+(?:[.,]\d+)?)")
_SCALE = re.compile(r"\s*(bilh\w*|milh\w*|mil|bi|mi|bn|mn|k|m|b)(?![a-z])", re.IGNORECASE)
# A percentage or percentage-point value ("29%", "4 p.p."): never a day / month count or a top-N.
_PCT_UNIT = re.compile(r"\s?(?:%|p\.\s?p\.|pp\b|pontos percentuais|percentage points)", re.IGNORECASE)


def _candidates(tok: str) -> list[float]:
    """Every plausible reading of a numeric token in pt-BR and en-US.

    "9,83" -> 9.83 · "1.234.567" -> 1234567 · "1,234.5" -> 1234.5 · "1.234" -> 1.234 or 1234 (ambiguous).
    """
    s = tok.strip().replace(" ", "")
    sign = -1.0 if s.startswith("-") else 1.0
    s = s.lstrip("+-")
    if not s:
        return []
    out: list[str] = []
    if "," in s and "." in s:
        out.append(s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", ""))
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        parts = s.split(sep)
        if len(parts) > 2:  # repeated separator -> thousands grouping
            out.append(s.replace(sep, ""))
        elif len(parts[1]) == 3:  # "1.234" / "1,234": thousands or decimal, depending on the locale
            out += [s.replace(sep, ""), s.replace(sep, ".")]
        else:
            out.append(s.replace(sep, "."))
    else:
        out.append(s)
    vals = []
    for x in out:
        try:
            vals.append(sign * float(x))
        except ValueError:
            continue
    return vals


def _scale_factor(word: str) -> float:
    w = word.lower()
    if w.startswith("bilh") or w in ("bi", "bn", "b"):
        return 1e9
    if w.startswith("milh") or w in ("mi", "mn", "m"):
        return 1e6
    return 1e3  # "mil", "k"


def _parse_number(tok: str) -> float | None:
    c = _candidates(tok)
    return c[0] if c else None


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
            out.extend(_candidates(m.group(0)))


def allowed_numbers(*sources: Any) -> list[float]:
    raw: list[float] = []
    for s in sources:
        _collect(s, raw)
    allowed: set[float] = set()
    for v in raw:
        a = abs(v)
        for k in (a, a * 100, a / 1e3, a / 1e6, a / 1e9):
            allowed.add(round(k, 6))
    return sorted(allowed)


def grounding_violations(text: str, allowed: list[float]) -> list[str]:
    """Numbers in ``text`` that do not match any allowed value (1.5% / 0.06 tolerance).

    Accepts en-US ("R$ 9.83M", "14.8%") and pt-BR ("R$ 9,83 mi", "14,8%", "1.234.567 unidades")
    formats; a scale word right after the number ("mi", "mil", "bi", "M", "K") is also understood.
    Small integers (≤ 31) and years pass as counts, except when they are percentages: a probability of
    "29%" must come from the facts like any other value.
    """
    bad = []
    for m in _NUM.finditer(text):
        cands = [abs(v) for v in _candidates(m.group(0))]
        if not cands:
            continue
        sc = _SCALE.match(text, m.end())
        if sc:
            f = _scale_factor(sc.group(1))
            cands += [c * f for c in cands]
        is_pct = _PCT_UNIT.match(text, m.end()) is not None
        ok = False
        for v in cands:
            plain_int = not sc and not is_pct and float(v).is_integer()
            if plain_int and (v <= 31 or 1900 <= v <= 2100):
                ok = True  # day / month counts, top-N, small integers, years
                break
            if any(abs(v - a) <= max(0.06, 0.015 * abs(a)) for a in allowed):
                ok = True
                break
        if not ok:
            bad.append(m.group(0))
    return bad
