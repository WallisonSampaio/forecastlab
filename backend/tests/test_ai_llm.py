"""AI analyst with the local LLM: latency contract, narration, model choice and LLM routing.

The HTTP layer of Ollama is mocked (``httpx.MockTransport``): no real model runs in pytest.
"""

from __future__ import annotations

import dataclasses
import json
import threading
import time

import httpx
import pandas as pd
import pytest

from app.ai import llm, narration
from app.ai.intents import parse

# ------------------------------------------------------------------------------ fake Ollama


def ndjson(content: str, pieces: int = 3) -> bytes:
    """Ollama /api/chat streaming body for ``content``."""
    step = max(1, len(content) // pieces)
    chunks = [content[i : i + step] for i in range(0, len(content), step)] or [""]
    lines = [json.dumps({"message": {"role": "assistant", "content": c}, "done": False}) for c in chunks]
    lines.append(json.dumps({"message": {"role": "assistant", "content": ""}, "done": True, "eval_count": 9}))
    return ("\n".join(lines) + "\n").encode()


class FakeOllama:
    def __init__(self, models: tuple[str, ...] = ("qwen3:1.7b",)) -> None:
        self.models = list(models)
        self.calls: list[tuple[str, dict | None]] = []
        self.chat_reply: object = json.dumps({"answer": "ok"})
        self.tags_error: Exception | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.url.path, body))
        if request.url.path == "/api/tags":
            if self.tags_error:
                raise self.tags_error
            return httpx.Response(200, json={"models": [{"name": m} for m in self.models]})
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={"model": body["model"], "done": True, "done_reason": "load"})
        if request.url.path == "/api/chat":
            reply = self.chat_reply(body) if callable(self.chat_reply) else self.chat_reply
            if isinstance(reply, Exception):
                raise reply
            if isinstance(reply, str):
                reply = ndjson(reply)
            return httpx.Response(200, content=reply)
        return httpx.Response(404)

    def chats(self) -> list[dict]:
        return [b for p, b in self.calls if p == "/api/chat"]

    def paths(self, path: str) -> list[dict]:
        return [b for p, b in self.calls if p == path]


def _join_background() -> None:
    thread = llm._status.get("thread")
    if thread is not None:
        thread.join(2)


@pytest.fixture
def ollama(monkeypatch):
    fake = FakeOllama()
    monkeypatch.setattr(
        llm,
        "settings",
        dataclasses.replace(llm.settings, ai_enabled=True, ollama_model="", ollama_timeout_s=90.0, ollama_num_thread=0),
    )
    monkeypatch.setattr(
        llm,
        "_client",
        lambda timeout: httpx.Client(
            base_url="http://ollama.test", transport=httpx.MockTransport(fake.handler), timeout=timeout
        ),
    )
    llm.reset_state()
    yield fake
    _join_background()
    llm.reset_state()


def _ask(client, question: str, **kw) -> dict:
    r = client.post("/api/ai/ask", json={"question": question, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _narrate_payload(a: dict) -> dict:
    return {
        "question": a["meta"]["question"],
        "lang": a["meta"]["language"],
        "filters": {},
        "answer": {k: a[k] for k in ("answer", "insights", "recommendations", "facts")},
    }


# ------------------------------------------------------------------------------ /api/ai/ask
def test_ask_never_calls_the_llm_and_answers_fast(api_client, ollama):
    llm.status(max_wait=2)  # the page loads /api/ai/status first
    t0 = time.perf_counter()
    a = _ask(api_client, "A meta de dezembro é realista?")
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.5, elapsed
    assert a["understood"] is True and a["interpretable"] is False
    assert a["meta"]["intent"]["name"] == "target_feasibility"
    assert a["narration"] == {"available": True, "model": "qwen3:1.7b", "reason": None}
    # Compact facts for /api/ai/narrate: formatted indicators + the numbers of the draft, <= 1.800 chars.
    facts = a["facts"]
    assert facts["indicadores"] and facts["numeros_do_rascunho"]
    assert len(json.dumps(facts, ensure_ascii=False)) <= narration.FACTS_MAX_CHARS
    assert a["meta"]["engine"] == "rule-based NLG" and a["meta"]["grounding"] == {"checked": False}

    # Not understood: help answer at once, flagged as interpretable by the local LLM.
    b = _ask(api_client, "bom dia")
    assert b["understood"] is False and b["interpretable"] is True
    assert b["meta"]["intent"] is None and b["answer"].startswith("Não consegui entender")
    assert b["narration"]["available"] is False and b["narration"]["reason"]
    assert ollama.chats() == []  # no generation at all on the ask path


def test_ask_without_llm_is_deterministic_and_not_interpretable(api_client):
    # FORECASTLAB_AI_ENABLED=false in the test environment.
    a = _ask(api_client, "Quanto vamos vender em janeiro?")
    assert a["understood"] is True
    assert a["narration"]["available"] is False
    assert "desativada" in a["narration"]["reason"]
    b = _ask(api_client, "bom dia")
    assert b["understood"] is False and b["interpretable"] is False
    # route_with_llm without a local model: plain help answer (the model was never consulted).
    c = _ask(api_client, "bom dia", route_with_llm=True)
    assert c["understood"] is False and c["meta"]["routing"]["status"] == "unavailable"
    assert c["answer"].startswith("Não consegui entender “bom dia”:")


def test_rankings_are_not_narrated(api_client, ollama):
    a = _ask(api_client, "quais clientes estão subestimados?")
    assert a["meta"]["intent"]["name"] == "bias_ranking"
    assert a["narration"]["available"] is False and "ranking" in a["narration"]["reason"]


def test_what_if_is_not_narrated(api_client, ollama):
    # Lever and outcome carry opposite signs; qwen3:1.7b wrote "a receita do cenário cai -5,0%" for a
    # +2,9% revenue scenario and "resulta em receita de R$ 94,30 mi" (the base, not the scenario).
    a = _ask(api_client, "E se o preço cair 5%?")
    assert a["meta"]["intent"]["name"] == "what_if"
    assert a["narration"]["available"] is False and "what-if" in a["narration"]["reason"]


def test_compact_facts_scope_is_portuguese():
    facts = narration.compact_facts(
        {"answer": "O WMAPE é 14,9%.", "filters": {"customer": "Litoral Market", "region": "Sul"}}, "pt"
    )
    assert facts["escopo"] == "cliente: Litoral Market, região: Sul"
    assert facts["numeros_do_rascunho"] == ["14,9%"]


# ------------------------------------------------------------------------------ /api/ai/narrate
def test_narrate_ok_swaps_the_answer_with_verified_numbers(api_client, ollama):
    a = _ask(api_client, "A meta de dezembro é realista?")
    n1, n2 = narration._draft_numbers(a["answer"])[:2]
    rewrite = f"Resumo executivo: os números-chave são {n1} e {n2}. O plano exige atenção da equipe comercial."
    ollama.chat_reply = json.dumps({"answer": rewrite})

    r = api_client.post("/api/ai/narrate", json=_narrate_payload(a))
    assert r.status_code == 200
    n = r.json()
    assert n["status"] == "ok", n
    assert n["answer"] == rewrite
    assert n["insights"] == a["insights"] and n["recommendations"] == a["recommendations"]
    assert n["model"] == "qwen3:1.7b" and isinstance(n["elapsed_s"], float)
    assert n["grounding"] == {"checked": True, "passed": True, "violations": []}

    payload = ollama.chats()[-1]
    assert payload["model"] == "qwen3:1.7b"
    assert payload["think"] is False and payload["stream"] is True and payload["keep_alive"] == "30m"
    assert payload["options"]["temperature"] == 0.1
    assert payload["options"]["num_ctx"] == 2048 and payload["options"]["num_predict"] == 320
    assert payload["format"]["type"] == "object" and "answer" in payload["format"]["properties"]
    user = payload["messages"][-1]["content"]
    facts_line = next(line for line in user.splitlines() if line.startswith("FATOS: "))
    assert len(facts_line) - len("FATOS: ") <= narration.FACTS_MAX_CHARS


def test_narrate_rejects_an_invented_number(api_client, ollama):
    a = _ask(api_client, "A meta de dezembro é realista?")
    ollama.chat_reply = json.dumps(
        {"answer": "Resumo executivo: o consenso chega a R$ 999,99 mi. O plano exige atenção."}
    )
    n = api_client.post("/api/ai/narrate", json=_narrate_payload(a)).json()
    assert n["status"] == "rejected"
    assert "999,99" in n["reason"] and "mantida a versão calculada" in n["reason"]
    assert n["grounding"]["passed"] is False and n["grounding"]["violations"] == ["999,99"]
    assert "answer" not in n


def test_narrate_rejects_a_changed_verdict_or_direction(api_client, ollama):
    a = _ask(api_client, "Quanto vamos vender em janeiro?")
    draft = {k: a[k] for k in ("answer", "insights", "recommendations", "facts")}
    # The computed answer says the consensus is below budget; the rewrite claims the opposite.
    assert "Orçamento" in a["answer"] and "(-" in a["answer"].split("Orçamento")[1][:40]
    ollama.chat_reply = json.dumps(
        {"answer": "O consenso de janeiro está acima do orçamento. Ótimo sinal para o plano."}
    )
    n = narration.narrate("Quanto vamos vender em janeiro?", "pt", {}, draft)
    assert n["status"] == "rejected" and "sentido" in n["reason"]

    ollama.chat_reply = json.dumps(
        {"answer": "A meta de janeiro é totalmente realista. Não há com o que se preocupar."}
    )
    n = narration.narrate("Quanto vamos vender em janeiro?", "pt", {}, draft)
    assert n["status"] == "rejected" and "classificação" in n["reason"]

    ollama.chat_reply = json.dumps({"answer": a["answer"]})  # a copy is not a refinement
    n = narration.narrate("Quanto vamos vender em janeiro?", "pt", {}, draft)
    assert n["status"] == "rejected" and "repetia" in n["reason"]


def test_narrate_rejects_an_invented_small_percentage(ollama):
    # Small integers pass as counts ("12 meses", "top 3"), but never as percentages: the computed
    # probability below is 4%, so "29%" is invented.
    draft = {
        "answer": "A meta de dezembro é AGRESSIVA: meta de R$ 12,15 mi vs consenso de R$ 9,98 mi. "
        "Probabilidade de atingir: 4%.",
        "insights": [],
        "recommendations": [],
        "facts": {},
    }
    ollama.chat_reply = json.dumps(
        {"answer": "A meta de dezembro é AGRESSIVA: R$ 12,15 mi contra R$ 9,98 mi, com 29% de chance em 12 meses."}
    )
    n = narration.narrate("A meta de dezembro é realista?", "pt", {}, draft)
    assert n["status"] == "rejected" and n["grounding"]["violations"] == ["29"]
    allowed = llm.allowed_numbers({"probabilidade": 0.04})
    assert llm.grounding_violations("Nos próximos 12 meses, a chance é de 4%; no top 3.", allowed) == []
    assert llm.grounding_violations("Chance de 29% ou 7 p.p. acima.", allowed) == ["29", "7"]


def test_narrate_hides_raw_ollama_errors(api_client, ollama):
    a = _ask(api_client, "A meta de dezembro é realista?")
    ollama.chat_reply = b'{"error": "model requires more system memory (5.2 GiB) than is available"}\n'
    n = api_client.post("/api/ai/narrate", json=_narrate_payload(a)).json()
    assert n["status"] == "rejected"
    assert n["reason"] == "A IA local falhou ao refinar o texto; mantida a versão calculada."


def test_narrate_timeout(api_client, ollama):
    a = _ask(api_client, "A meta de dezembro é realista?")
    ollama.chat_reply = httpx.ReadTimeout("slow CPU")
    n = api_client.post("/api/ai/narrate", json=_narrate_payload(a)).json()
    assert n["status"] == "timeout"
    assert n["reason"] == "A IA local não terminou em 90 s; mantida a versão calculada."
    assert n["model"] == "qwen3:1.7b"


def test_narrate_is_cancelled_by_a_newer_question(ollama):
    def slow_stream(_body):
        def gen():
            yield ndjson('{"answer": "Primeira parte', pieces=1).split(b"\n")[0] + b"\n"
            narration.new_generation()  # the user asked something else meanwhile
            time.sleep(0.3)
            yield b'{"message": {"content": " resto."}, "done": false}\n'
            yield b'{"done": true}\n'

        return gen()

    ollama.chat_reply = slow_stream
    draft = {"answer": "O consenso de janeiro é R$ 8,16 mi.", "insights": [], "recommendations": [], "facts": {}}
    n = narration.narrate("Quanto vamos vender em janeiro?", "pt", {}, draft)
    assert n["status"] == "cancelled" and n["reason"]


def test_narrate_when_ai_is_disabled(api_client):
    a = _ask(api_client, "A meta de dezembro é realista?")
    n = api_client.post("/api/ai/narrate", json=_narrate_payload(a)).json()
    assert n["status"] == "unavailable" and "desativada" in n["reason"]
    r = api_client.post("/api/ai/narrate", json={"question": "x", "answer": {"answer": " "}})
    assert r.status_code == 400 and r.json()["detail"] == "Não há resposta calculada para refinar."


def test_parse_rewrite_salvages_a_cut_answer():
    assert narration.parse_rewrite('{"answer": "Frase completa. Outra frase cort')["answer"] == "Frase completa."
    assert narration.parse_rewrite('{"answer": "Tudo certo."}')["complete"] is True
    assert narration.parse_rewrite("lixo") is None


# ------------------------------------------------------------------------------ model choice / status
@pytest.mark.parametrize(
    ("models", "configured", "expected"),
    [
        (["llama3.2:3b", "qwen3:1.7b"], None, "qwen3:1.7b"),
        (["qwen3:4b-instruct-2507-q4_K_M", "llama3.2:3b"], None, "llama3.2:3b"),
        (["qwen3:4b", "qwen3:4b-instruct-2507-q4_K_M"], None, "qwen3:4b-instruct-2507-q4_K_M"),
        (["nomic-embed-text:latest", "mistral:7b"], None, "mistral:7b"),
        ([], None, None),
        (["qwen3:1.7b", "llama3.2:3b"], "llama3.2:3b", "llama3.2:3b"),
        (["phi4:latest", "qwen3:1.7b"], "phi4", "phi4:latest"),
        (["qwen3:1.7b"], "phi4", "qwen3:1.7b"),
    ],
)
def test_model_preference(models, configured, expected):
    model, note = llm.select_model(models, configured)
    assert model == expected
    if configured and expected != configured and not (expected or "").startswith(configured):
        assert "OLLAMA_MODEL" in note
    else:
        assert note is None


def test_status_picks_the_preferred_model_and_warms_it_once(ollama):
    ollama.models = ["llama3.2:3b", "qwen3:4b-instruct-2507-q4_K_M", "qwen3:1.7b"]
    st = llm.status(max_wait=2)
    assert st["available"] is True and st["model"] == "qwen3:1.7b" and st["reason"] is None
    assert st["models"] == ollama.models
    for _ in range(50):  # the warm-up runs in a daemon thread
        if llm._warm["state"] == "ready":
            break
        time.sleep(0.02)
    llm.status(max_wait=2)
    warm = ollama.paths("/api/generate")
    assert len(warm) == 1 and warm[0]["model"] == "qwen3:1.7b" and warm[0]["keep_alive"] == "30m"
    assert llm.status()["warmup"]["state"] == "ready"


def test_status_reasons_are_portuguese(ollama, monkeypatch):
    ollama.models = []
    st = llm.status(force=True, max_wait=2)
    assert st["available"] is False and st["reason"].startswith("Nenhum modelo baixado no Ollama")

    llm.reset_state()
    ollama.tags_error = httpx.ConnectError("refused")
    st = llm.status(force=True, max_wait=2)
    assert st["available"] is False and st["reason"].startswith("Ollama não encontrado em ")

    monkeypatch.setattr(llm, "settings", dataclasses.replace(llm.settings, ai_enabled=False))
    assert llm.status()["reason"] == "IA local desativada (FORECASTLAB_AI_ENABLED=false)."


def test_status_never_blocks_the_request_path(ollama):
    gate = threading.Event()
    original = ollama.handler

    def slow(request):
        if request.url.path == "/api/tags":
            gate.wait(2)
        return original(request)

    ollama.handler = slow
    t0 = time.perf_counter()
    st = llm.status(max_wait=0.2)
    assert time.perf_counter() - t0 < 1.0
    assert st["available"] is False and st.get("checking") is True
    gate.set()
    _join_background()
    assert llm.status(max_wait=0.2)["available"] is True


# ------------------------------------------------------------------------------ route_with_llm
def _classification(intent: str, **kw) -> str:
    base = {"intent": intent, "dimension": "none", "direction": "none", "metric": "none", "entities": [], "months": []}
    return json.dumps({**base, **kw})


def test_route_with_llm_unknown_intent_gives_the_help_answer(api_client, ollama):
    ollama.chat_reply = _classification("hack_the_database")
    a = _ask(api_client, "bom dia", route_with_llm=True)
    assert a["understood"] is False and a["interpretable"] is False
    assert a["meta"]["intent"] is None
    assert a["answer"].startswith("Não consegui entender “bom dia”, nem com a ajuda da IA local")
    assert a["meta"]["routing"]["status"] == "unknown"
    payload = ollama.chats()[-1]
    assert payload["options"]["num_predict"] <= 120 and payload["think"] is False
    assert "summary" in payload["format"]["properties"]["intent"]["enum"]


def test_route_with_llm_valid_intent_runs_the_handler(api_client, ollama):
    ollama.chat_reply = _classification("summary")
    a = _ask(api_client, "Estamos indo bem?", route_with_llm=True)
    assert a["understood"] is True
    assert a["meta"]["intent"]["name"] == "summary" and a["meta"]["intent"]["source"] == "llm"
    assert a["meta"]["routing"]["status"] == "ok" and a["answer"]
    assert a["narration"]["available"] is True


def test_route_with_llm_validates_entities(api_client, ollama):
    ollama.chat_reply = _classification("entity_overview", entities=["Cliente Fantasma"])
    a = _ask(api_client, "bom dia", route_with_llm=True)
    assert a["understood"] is False and a["meta"]["routing"]["status"] == "unknown"

    ollama.chat_reply = _classification("entity_overview", entities=["vila verde"], dimension="drop table")
    a = _ask(api_client, "bom dia", route_with_llm=True)
    assert a["meta"]["intent"]["name"] == "entity_overview"
    assert a["meta"]["intent"]["filters"] == {"customer": "Vila Verde Mercados"}
    assert a["meta"]["intent"]["dimension"] is None


def test_route_with_llm_timeout_falls_back_to_help(api_client, ollama):
    ollama.chat_reply = httpx.ReadTimeout("slow")
    a = _ask(api_client, "bom dia", route_with_llm=True)
    assert a["understood"] is False and a["meta"]["routing"]["status"] == "timeout"


# ------------------------------------------------------------------------------ deep-link questions (spec §2.2.3 / §4.3.3)
MEMBERS = {
    "region": ["Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"],
    "channel": ["Varejo Moderno", "Atacarejo", "Varejo Tradicional", "E-commerce", "Farma"],
    "customer": ["Atlas Hipermercados", "Rede Horizonte Supermercados", "Litoral Market", "ClickCesta Online"],
    "category": ["Bebidas", "Snacks", "Cuidados Pessoais", "Limpeza"],
    "brand": ["AquaViva", "Frutalle", "Crocantes"],
    "sku": ["SKU-10101", "SKU-20102"],
    "product_map": [["SKU-10101", "AquaViva Água Mineral 500ml"], ["SKU-20102", "Crocantes Batata Queijo 90g"]],
}
HORIZON = list(pd.date_range("2026-10-01", periods=12, freq="MS"))
LAST = pd.Timestamp("2026-09-01")


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("Quais os principais riscos?", "risks"),
        ("Quanto vendemos nos últimos 12 meses?", "forecast_value"),
        ("Quais ajustes comerciais pioraram a acurácia?", "fva_overrides"),
        ("Quais clientes estão superestimados?", "bias_ranking"),
        ("Quais clientes estão subestimados?", "bias_ranking"),
        ("Por que o forecast de dezembro de 2026 está abaixo do orçamento?", "budget_gap"),
        ("Por que o forecast de março de 2027 está acima do orçamento?", "budget_gap"),
        ("Como está o cliente Litoral Market?", "entity_overview"),
        ("Como está o cliente Rede Horizonte Supermercados?", "entity_overview"),
        ("Como está a categoria Bebidas?", "entity_overview"),
        ("Como está o SKU SKU-10101?", "entity_overview"),
        ("Como está a região Sul?", "entity_overview"),
        ("Como está o canal E-commerce?", "entity_overview"),
        ("A meta é realista?", "target_feasibility"),
        ("Onde estamos abaixo do orçamento?", "budget_gap"),
        ("Onde estamos acima do orçamento?", "budget_gap"),
        ("Qual o WMAPE de Atlas Hipermercados?", "metric_lookup"),
    ],
)
def test_deep_link_questions_keep_their_intents(question, intent):
    it = parse(question, MEMBERS, HORIZON, LAST)
    assert it is not None and it.name == intent, (question, it and it.name)
    if question.startswith("Por que o forecast de dezembro de 2026"):
        assert it.months == ["2026-12-01"]
    if question.startswith("Quanto vendemos nos últimos 12 meses"):
        assert it.months and max(it.months) <= "2026-09-01"
