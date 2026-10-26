"""AI Demand Analyst: natural-language understanding (PT-BR first), entities, periods, levers and grounding."""

import re

import pandas as pd
import pytest

from app.ai import nlg
from app.ai.analyst import SUGGESTIONS
from app.ai.intents import detect_language, extract_entities, extract_levers, extract_months, parse
from app.ai.llm import allowed_numbers, grounding_violations

MEMBERS = {
    "region": ["Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"],
    "channel": ["Varejo Moderno", "Atacarejo", "Varejo Tradicional", "E-commerce", "Farma"],
    "customer": [
        "Atlas Hipermercados",
        "Rede Horizonte Supermercados",
        "MaxiCompra Atacarejo",
        "Nordeste Atacadista",
        "Vila Verde Mercados",
        "ClickCesta Online",
        "Litoral Market",
        "CuraMais Farmácias",
        "Ponto Certo Conveniência",
        "Planalto Atacado",
    ],
    "category": ["Bebidas", "Snacks", "Cuidados Pessoais", "Limpeza"],
    "brand": ["AquaViva", "Frutalle", "Crocantes", "NutriBar", "PuraPele", "Brisa", "Fresco"],
    "sku": [
        "SKU-10101",
        "SKU-10103",
        "SKU-10202",
        "SKU-20102",
        "SKU-20202",
        "SKU-30102",
        "SKU-30201",
        "SKU-30202",
        "SKU-40201",
    ],
    "product_map": [
        ["SKU-10101", "AquaViva Água Mineral 500ml"],
        ["SKU-10103", "AquaViva Água Mineral 1,5L"],
        ["SKU-10202", "Frutalle Suco de Uva 1L"],
        ["SKU-20102", "Crocantes Batata Queijo 90g"],
        ["SKU-20202", "NutriBar Proteína 45g"],
        ["SKU-30102", "PuraPele Protetor Solar FPS50 120ml"],
        ["SKU-30201", "Brisa Desodorante Roll-on 50ml"],
        ["SKU-30202", "Brisa Desodorante Aerosol 150ml"],
        ["SKU-40201", "Fresco Aromatizador Lavanda 360ml"],
    ],
}
HORIZON = list(pd.date_range("2026-10-01", periods=12, freq="MS"))
LAST = pd.Timestamp("2026-09-01")


def _parse(q):
    return parse(q, MEMBERS, HORIZON, LAST)


# ------------------------------------------------------------------------------- intents (PT-BR)
@pytest.mark.parametrize(
    ("question", "intent", "expect"),
    [
        # Target feasibility
        ("a meta de dezembro como está?", "target_feasibility", {"months": ["2026-12-01"]}),
        ("a meta de dezembro como está ?", "target_feasibility", {"months": ["2026-12-01"]}),
        ("como está a meta de dezembro", "target_feasibility", {"months": ["2026-12-01"]}),
        ("vamos bater a meta?", "target_feasibility", {}),
        (
            "qual a chance de atingir a meta do Atlas?",
            "target_feasibility",
            {"filters": {"customer": "Atlas Hipermercados"}},
        ),
        ("A meta de dezembro é realista?", "target_feasibility", {"months": ["2026-12-01"]}),
        ("vamos bater a meta de dezembro?", "target_feasibility", {"months": ["2026-12-01"]}),
        # A closed month: actual vs target (forecast_value past branch), not a feasibility assessment
        ("batemos a meta de agosto?", "forecast_value", {"months": ["2026-08-01"]}),
        (
            "a meta do 1º trimestre é realista?",
            "target_feasibility",
            {"months": ["2027-01-01", "2027-02-01", "2027-03-01"]},
        ),
        # Forecast value
        ("quanto vamos vender em janeiro?", "forecast_value", {"months": ["2027-01-01"]}),
        ("previsão de vendas do protetor solar", "forecast_value", {"filters": {"sku": "SKU-30102"}}),
        (
            "qual a previsão para o SKU-20102 em janeiro?",
            "forecast_value",
            {"filters": {"sku": "SKU-20102"}, "months": ["2027-01-01"]},
        ),
        (
            "previsão de receita do Sul no próximo trimestre",
            "forecast_value",
            {"filters": {"region": "Sul"}, "months": ["2027-01-01", "2027-02-01", "2027-03-01"]},
        ),
        (
            "quanto vamos faturar nos próximos 3 meses?",
            "forecast_value",
            {"months": ["2026-10-01", "2026-11-01", "2026-12-01"]},
        ),
        (
            "qual o forecast da AquaViva para dezembro?",
            "forecast_value",
            {"filters": {"brand": "AquaViva"}, "months": ["2026-12-01"]},
        ),
        (
            "qual a previsão da nutribar proteína em março?",
            "forecast_value",
            {"filters": {"sku": "SKU-20202"}, "months": ["2027-03-01"]},
        ),
        ("previsão do próximo mês", "forecast_value", {"months": ["2026-11-01"]}),
        ("qual o consenso de janeiro?", "forecast_value", {"months": ["2027-01-01"]}),
        ("qual o P90 de dezembro?", "forecast_value", {"months": ["2026-12-01"]}),
        ("cenário pessimista", "forecast_value", {}),
        ("previsão para o Natal", "forecast_value", {"months": ["2026-12-01"]}),
        ("quanto o Atlas vai comprar em janeiro?", "forecast_value", {"months": ["2027-01-01"]}),
        # Past tense -> latest closed month (actuals), not the forecast horizon
        ("quanto vendemos em setembro?", "forecast_value", {"months": ["2026-09-01"]}),
        ("como foram as vendas de agosto?", "forecast_value", {"months": ["2026-08-01"]}),
        ("quanto vamos vender em setembro?", "forecast_value", {"months": ["2027-09-01"]}),
        # Metric lookup
        (
            "qual o WMAPE da Atlas?",
            "metric_lookup",
            {"filters": {"customer": "Atlas Hipermercados"}, "metric": "wmape"},
        ),
        ("qual o viés do SKU-10101?", "metric_lookup", {"filters": {"sku": "SKU-10101"}, "metric": "bias"}),
        ("acurácia do canal E-commerce", "metric_lookup", {"filters": {"channel": "E-commerce"}, "metric": "accuracy"}),
        ("qual a acurácia geral?", "metric_lookup", {"filters": {}, "metric": "accuracy"}),
        # Accuracy / bias exist only for closed months: month names map to the backtest window
        (
            "qual o viés da Vila Verde em dezembro?",
            "metric_lookup",
            {"filters": {"customer": "Vila Verde Mercados"}, "months": ["2025-12-01"], "metric": "bias"},
        ),
        ("qual a acurácia em março?", "metric_lookup", {"months": ["2026-03-01"]}),
        ("qual o viés em dez/26?", "metric_lookup", {"months": ["2026-12-01"]}),
        (
            "qual a acurácia do último trimestre?",
            "metric_lookup",
            {"months": ["2026-07-01", "2026-08-01", "2026-09-01"]},
        ),
        ("o forecast está superestimado?", "metric_lookup", {"metric": "bias"}),
        ("o forecast está bom?", "metric_lookup", {}),
        ("estamos errando muito?", "metric_lookup", {"metric": "wmape"}),
        # Rankings
        ("qual cliente tem o maior viés?", "bias_ranking", {"dimension": "customer", "direction": "abs"}),
        ("quais produtos estão superestimados?", "bias_ranking", {"dimension": "sku", "direction": "over"}),
        ("quais clientes estão subestimados?", "bias_ranking", {"dimension": "customer", "direction": "under"}),
        ("Quais clientes estão superestimados?", "bias_ranking", {"direction": "over"}),
        ("pior acurácia por região", "worst_accuracy", {"dimension": "region", "direction": "worst"}),
        ("quais SKUs têm o maior erro?", "worst_accuracy", {"dimension": "sku"}),
        ("qual cliente erra mais?", "worst_accuracy", {"dimension": "customer", "direction": "worst"}),
        ("qual sku tem o pior forecast?", "worst_accuracy", {"dimension": "sku"}),
        ("top 5 piores skus", "worst_accuracy", {"dimension": "sku"}),
        (
            "quais clientes têm pior acurácia em julho?",
            "worst_accuracy",
            {"dimension": "customer", "months": ["2026-07-01"]},
        ),
        # Budget
        ("estamos abaixo do orçamento?", "budget_gap", {}),
        ("onde estamos abaixo do orçamento no Nordeste?", "budget_gap", {"filters": {"region": "Nordeste"}}),
        ("Onde estamos abaixo do orçamento?", "budget_gap", {}),
        # What-if
        ("o que acontece se o preço cair 5%?", "what_if", {"levers": {"price": -0.05}}),
        (
            "e se a distribuição aumentar 10% no Sul?",
            "what_if",
            {"levers": {"distribution": 0.10}, "filters": {"region": "Sul"}},
        ),
        ("simule uma promoção em dezembro", "what_if", {"levers": {"promotion": True}, "months": ["2026-12-01"]}),
        ("e se as vendas crescerem 10%?", "what_if", {"levers": {"market_growth": 0.10}}),
        ("e se perdermos 10% de distribuição?", "what_if", {"levers": {"distribution": -0.10}}),
        # Models / FVA / risks
        ("qual modelo funciona melhor para o SKU-20102?", "best_model", {"filters": {"sku": "SKU-20102"}}),
        ("quais modelos são campeões com mais frequência?", "model_distribution", {}),
        ("quais ajustes pioraram o forecast?", "fva_overrides", {}),
        ("os ajustes comerciais agregaram valor?", "fva_overrides", {}),
        ("o consenso é melhor que o estatístico?", "fva_overrides", {}),
        ("quais planejadores pioram o forecast?", "fva_overrides", {"dimension": "planner"}),
        ("quais eventos pioraram a acurácia?", "fva_overrides", {"dimension": "event_type"}),
        ("por que o modelo escolhido foi ETS?", "best_model", {}),
        ("quais os principais riscos?", "risks", {}),
        ("tem algum alerta crítico para o Atlas?", "risks", {"filters": {"customer": "Atlas Hipermercados"}}),
        ("o que devo olhar primeiro?", "risks", {}),
        ("o que pode dar errado?", "risks", {}),
        # Entity overview
        ("como está o cliente Litoral Market?", "entity_overview", {"filters": {"customer": "Litoral Market"}}),
        ("me fale do canal E-commerce", "entity_overview", {"filters": {"channel": "E-commerce"}}),
        ("e a região Nordeste?", "entity_overview", {"filters": {"region": "Nordeste"}}),
        ("me fale da marca AquaViva", "entity_overview", {"filters": {"brand": "AquaViva"}}),
        ("como está a Horizonte?", "entity_overview", {"filters": {"customer": "Rede Horizonte Supermercados"}}),
        ("Nordeste Atacadista", "entity_overview", {"filters": {"customer": "Nordeste Atacadista"}}),
        ("Atlas", "entity_overview", {"filters": {"customer": "Atlas Hipermercados"}}),
        # Drivers / summary / patterns
        ("por que dezembro cresce?", "forecast_drivers", {"months": ["2026-12-01"]}),
        ("o que está puxando o crescimento em julho?", "forecast_drivers", {"months": ["2027-07-01"]}),
        ("por que a previsão de dezembro é tão alta?", "forecast_drivers", {"months": ["2026-12-01"]}),
        ("qual o impacto dos eventos?", "forecast_drivers", {}),
        ("como está o forecast?", "summary", {}),
        ("quantas séries temos?", "series_types", {}),
        ("resuma o plano", "summary", {}),
        ("como estão as vendas?", "summary", {}),
        ("quais séries são intermitentes?", "series_types", {}),
    ],
)
def test_portuguese_questions_are_understood(question, intent, expect):
    it = _parse(question)
    assert it is not None, question
    assert it.name == intent, (question, it.name, it.scores)
    assert it.language == "pt"
    if "filters" in expect:
        assert it.filters == expect["filters"], (question, it.filters)
    if "months" in expect:
        assert it.months == expect["months"], (question, it.months)
    for key in ("metric", "dimension", "direction"):
        if key in expect:
            assert getattr(it, key) == expect[key], (question, key, getattr(it, key))
    if "levers" in expect:
        assert it.levers.keys() == expect["levers"].keys()
        for k, v in expect["levers"].items():
            assert it.levers[k] == pytest.approx(v) if not isinstance(v, bool) else it.levers[k] is v


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("What is driving forecast growth in July?", "forecast_drivers"),
        ("Which SKUs have the worst forecast accuracy?", "worst_accuracy"),
        ("Which customers are overforecasted?", "bias_ranking"),
        ("Is December target realistic?", "target_feasibility"),
        ("Will we hit the December target?", "target_feasibility"),
        ("How much did we sell in August?", "forecast_value"),
        ("Which model performs best for SKU-20102?", "best_model"),
        ("What happens if distribution increases by 10%?", "what_if"),
        ("Which commercial overrides reduced accuracy?", "fva_overrides"),
        ("Which models are champions most often?", "model_distribution"),
        ("Where are we below budget?", "budget_gap"),
        ("What are the main risks?", "risks"),
        ("How much will we sell in December?", "forecast_value"),
        ("What is the WMAPE for Atlas?", "metric_lookup"),
        ("Tell me about the South region", "entity_overview"),
    ],
)
def test_english_questions_are_understood(question, intent):
    it = _parse(question)
    assert it is not None and it.name == intent, (question, it and it.name)
    assert it.language == "en"


def test_never_generic_help_when_something_is_recognized():
    # A lone month, entity or metric word is enough to answer something useful.
    assert _parse("dezembro").name == "forecast_value"
    assert _parse("Litoral").name == "entity_overview"
    assert _parse("WMAPE?").name == "metric_lookup"
    assert _parse("nutribar proteína").filters == {"sku": "SKU-20202"}
    # Nothing recognized -> None (the analyst answers with help + examples).
    assert _parse("hello there") is None
    assert _parse("bom dia") is None
    assert _parse("está certo isso?") is None


# ------------------------------------------------------------------------------- entities
def test_entities_aliases_and_false_positives():
    ent = lambda q: extract_entities(q, MEMBERS)  # noqa: E731
    assert ent("como está o Atlas?") == {"customer": "Atlas Hipermercados"}
    assert ent("e a Litoral?") == {"customer": "Litoral Market"}
    assert ent("vendas da clickcesta") == {"customer": "ClickCesta Online"}
    assert ent("como vai o Atlass") == {"customer": "Atlas Hipermercados"}  # fuzzy
    assert ent("Nordeste Atacadista") == {"customer": "Nordeste Atacadista"}  # not the region
    assert ent("clientes do Nordeste") == {"region": "Nordeste"}
    assert ent("região centro oeste") == {"region": "Centro-Oeste"}
    assert ent("canal ecommerce") == {"channel": "E-commerce"}
    assert ent("in the southeast") == {"region": "Sudeste"}
    assert ent("personal care sales") == {"category": "Cuidados Pessoais"}
    assert ent("protetor solar") == {"sku": "SKU-30102"}
    assert ent("suco de uva") == {"sku": "SKU-10202"}
    assert ent("aqua viva") == {"brand": "AquaViva"}
    assert ent("água mineral") == {"brand": "AquaViva"}  # two SKUs -> their common brand
    assert ent("previsão do desodorante") == {"brand": "Brisa"}  # generic word of one brand's SKUs
    assert ent("desodorante aerosol") == {"sku": "SKU-30202"}
    assert ent("sku 20102") == {"sku": "SKU-20102"}
    assert ent("o 20102 vende bem?") == {"sku": "SKU-20102"}
    # Common words must not become entities.
    assert ent("qual o horizonte do forecast?") == {}
    assert ent("resultado da consulta e do consumo") == {}  # "sul" inside words
    assert ent("está certo, ponto final") == {}
    assert ent("um aroma fresco") == {}
    assert ent("marca Fresco") == {"brand": "Fresco"}
    assert ent("fresco aromatizador lavanda") == {"sku": "SKU-40201"}
    assert ent("e o ponto certo?") == {"customer": "Ponto Certo Conveniência"}
    assert ent("vila verde") == {"customer": "Vila Verde Mercados"}


# ------------------------------------------------------------------------------- periods
def test_months_and_periods():
    months = lambda q: extract_months(q, HORIZON, LAST)  # noqa: E731
    assert months("previsão de dezembro") == ["2026-12-01"]
    assert months("em dez/26") == ["2026-12-01"]
    assert months("previsão de março") == ["2027-03-01"]
    assert months("em julho") == ["2027-07-01"]
    assert months("abril passado") == months("último abril") == ["2026-04-01"]
    assert months("este mês") == ["2026-10-01"]
    assert months("próximo mês") == ["2026-11-01"]
    assert months("T1") == months("Q1") == months("primeiro trimestre") == ["2027-01-01", "2027-02-01", "2027-03-01"]
    assert months("próximo trimestre") == ["2027-01-01", "2027-02-01", "2027-03-01"]
    assert months("próximos 6 meses") == [d.strftime("%Y-%m-01") for d in HORIZON[:6]]
    assert months("próximos 12 meses") == []  # full horizon
    assert months("dezembro de 2027") == ["2027-12-01"]
    assert months("previsão para o Natal") == ["2026-12-01"]
    assert months("meta da Black Friday") == ["2026-11-01"]
    assert months("último trimestre") == ["2026-07-01", "2026-08-01", "2026-09-01"]
    # Month abbreviations that are also words are ignored without context.
    assert months("set the price") == []
    assert months("o mar está calmo") == []
    assert months("aumentar dez por cento") == []
    assert months("tudo out of stock") == []


def test_past_month_maps_to_last_actual_year():
    # Horizon covers Oct/2026-Sep/2027: every month is in the future; with a short horizon, past months
    # resolve to the latest closed occurrence.
    short = HORIZON[:3]
    assert extract_months("como foi março?", short, LAST) == ["2026-03-01"]


# ------------------------------------------------------------------------------- levers
def test_lever_extraction_signs():
    assert extract_levers("What happens if distribution increases by 10%?") == {"distribution": 0.10}
    lv = extract_levers("E se o preço cair 5% e a distribuição aumentar 10%?")
    assert lv["price"] == pytest.approx(-0.05) and lv["distribution"] == pytest.approx(0.10)
    lv = extract_levers("reduce price by 3% and raise marketing 20%")
    assert lv["price"] == pytest.approx(-0.03) and lv["marketing"] == pytest.approx(0.20)
    assert extract_levers("um desconto de 5%") == {"price": pytest.approx(-0.05)}
    assert extract_levers("aumentar dez por cento o preço") == {"price": pytest.approx(0.10)}
    assert extract_levers("e se fizermos uma promoção?") == {"promotion": True}
    assert extract_levers("e se perdermos 10% de distribuição?") == {"distribution": pytest.approx(-0.10)}
    # Entity names are not levers ("Market" in Litoral Market).
    assert extract_levers("como está o cliente Litoral Market?") == {}


def test_language_detection_defaults_to_portuguese():
    assert detect_language("Is December target realistic?") == "en"
    assert detect_language("A meta de dezembro é realista?") == "pt"
    assert detect_language("WMAPE Atlas") == "pt"
    assert detect_language("") == "pt"


# ------------------------------------------------------------------------------- nlg / suggestions
def test_ptbr_formatting_and_code_labels():
    assert nlg.money(9_828_614.6, "pt") == "R$ 9,83 mi"
    assert nlg.money(45_600, "pt") == "R$ 45,6 mil"
    assert nlg.money(-2_000_000, "pt") == "-R$ 2,00 mi"
    assert nlg.money(9_828_614.6, "en") == "R$ 9.83M"
    assert nlg.pct(0.148, "pt") == "14,8%"
    assert nlg.pct(0.021, "pt", signed=True) == "+2,1%"
    assert nlg.num(1_234_567, "pt") == "1.234.567"
    assert nlg.units(12_345, "pt") == "12,3 mil unidades"
    assert nlg.month_name("2026-12-01", "pt") == "dezembro/2026"
    assert nlg.month_short("2026-12-01", "pt") == "dez/26"
    assert nlg.period_text(["2027-01-01", "2027-02-01", "2027-03-01"], "pt") == "1º trimestre de 2027"
    q1 = ["2027-01-01", "2027-02-01", "2027-03-01"]
    assert nlg.period_prep(q1, "pt", "de") == "do 1º trimestre de 2027"  # "A meta do 1º trimestre ..."
    assert nlg.period_prep(q1, "pt", "em") == "no 1º trimestre de 2027"
    assert nlg.period_prep(None, "pt", "de") == "dos próximos 12 meses"
    assert nlg.period_prep(["2026-12-01"], "pt", "para") == "para dezembro/2026"
    assert nlg.period_prep([f"2026-{m:02d}-01" for m in range(1, 13)], "pt", "em") == "em 2026"
    assert nlg.series_type("Seasonal", "pt") == "Sazonal" and nlg.series_type("Stable", "pt") == "Estável"
    assert nlg.model_name("Seasonal Naive", "pt") == "Ingênuo sazonal"
    assert nlg.model_name("Moving Average", "pt") == "Média Móvel"
    assert nlg.model_name("Regression", "pt") == "Regressão"
    assert nlg.class_label("STRETCH", "pt") == "DESAFIADORA"
    assert nlg.bias_class("Over", "pt") == "Superestimado"
    assert nlg.confidence("High", "pt") == "Alta"


def test_suggestions_cover_the_new_intents():
    pt = SUGGESTIONS["pt"]
    assert 8 <= len(pt) <= 10 and len(SUGGESTIONS["en"]) >= 8
    names = {_parse(q).name for q in pt}
    assert {"forecast_value", "metric_lookup", "entity_overview", "target_feasibility", "what_if"} <= names
    assert all(_parse(q) is not None for q in SUGGESTIONS["en"])


# ------------------------------------------------------------------------------- grounding
def test_grounding_guard_rejects_invented_numbers():
    facts = {"consensus": 9_828_614.6, "probability": 0.0106, "growth": -0.0102}
    allowed = allowed_numbers(facts)
    assert grounding_violations("Consensus is R$ 9.83M with a 1.1% probability (growth -1.0%).", allowed) == []
    assert grounding_violations("Consensus is R$ 12.4M and growth is 37%.", allowed) == ["12.4", "37"]


def test_grounding_guard_accepts_ptbr_numbers():
    facts = {"consensus": 9_828_614.6, "probability": 0.0106, "growth": -0.0102, "units": 1_234_567, "events": 45_600}
    allowed = allowed_numbers(facts)
    ok = (
        "O consenso é de R$ 9,83 mi, com probabilidade de 1,1% (crescimento de -1,0%), 1.234.567 unidades "
        "e eventos de R$ 45,6 mil (1,23 mi de unidades; P10–P90; SKU-20102 em dez/26)."
    )
    assert grounding_violations(ok, allowed + allowed_numbers("SKU-20102")) == []
    bad = grounding_violations("O consenso é de R$ 12,4 mi, crescimento de 37% e 2.345.678 unidades.", allowed)
    assert bad == ["12,4", "37", "2.345.678"]
    # A scale word does not make an invented small number acceptable.
    assert grounding_violations("Receita de R$ 12 mi.", allowed) == ["12"]


# ------------------------------------------------------------------------------- end to end
def test_analyst_end_to_end(api_client):
    r = api_client.post("/api/ai/ask", json={"question": "Is December target realistic?"}).json()
    assert r["meta"]["intent"]["name"] == "target_feasibility"
    assert r["answer"] and r["metrics"] and r["chart"]["type"] == "bar"
    assert set(r) >= {"answer", "insights", "metrics", "chart", "recommendations", "filters"}
    r = api_client.post("/api/ai/ask", json={"question": "What happens if distribution increases by 10%?"}).json()
    assert r["meta"]["intent"]["levers"] == {"distribution": 0.1}
    assert r["metrics"][1]["value"] > 0


ENGLISH_CODES = re.compile(
    r"\b(Seasonal Naive|Moving Average|Stable|Seasonal|Intermittent|Trending|Declining|Volatile)\b"
)


def test_analyst_end_to_end_portuguese(api_client):
    ask = lambda q: api_client.post("/api/ai/ask", json={"question": q}).json()  # noqa: E731

    r = ask("a meta de dezembro como está ?")
    assert r["meta"]["intent"]["name"] == "target_feasibility"
    assert r["meta"]["language"] == "pt"
    assert "meta" in r["answer"].lower() and "R$" in r["answer"]
    assert any(m["label"] == "Meta" for m in r["metrics"])

    r = ask("Quanto vamos vender em janeiro?")
    assert r["meta"]["intent"]["name"] == "forecast_value"
    assert r["answer"].startswith("A previsão de consenso para janeiro/")
    assert r["metrics"][0]["label"] == "Consenso" and r["metrics"][0]["value"] > 0
    assert r["chart"] is not None and r["table"]["columns"][0] == "Mês"

    r = ask("Qual o WMAPE da Vila Verde?")
    assert r["meta"]["intent"]["name"] == "metric_lookup"
    assert r["filters"] == {"customer": "Vila Verde Mercados"}
    assert "WMAPE" in r["answer"] and "%" in r["answer"]

    r = ask("a meta do próximo trimestre é realista?")
    assert r["meta"]["intent"]["name"] == "target_feasibility"
    assert r["answer"].startswith("A meta do ") and "trimestre de" in r["answer"]

    r = ask("como está o cliente CuraMais?")
    assert r["meta"]["intent"]["name"] == "entity_overview"
    assert r["filters"] == {"customer": "CuraMais Farmácias"}
    assert any(m["label"] == "Consenso 12M" for m in r["metrics"])

    # Accuracy for a month name uses the closed month of the backtest, not the future one.
    r = ask("qual o viés da Vila Verde em dezembro?")
    assert r["meta"]["intent"]["name"] == "metric_lookup"
    assert r["meta"]["intent"]["months"][0] <= r["meta"]["intent"]["months"][-1]
    assert "Não há resultados" not in r["answer"] and "dezembro/" in r["answer"]

    # Past tense -> actual sales of the latest closed month.
    r = ask("como foram as vendas de agosto?")
    assert r["meta"]["intent"]["name"] == "forecast_value"
    assert r["answer"].startswith("Em agosto/") and "realizadas" in r["answer"]

    r = ask("bom dia")
    assert r["meta"]["intent"] is None
    assert r["answer"].startswith("Não consegui entender")
    assert len(r["recommendations"]) == 4 and all(q.endswith("?") for q in r["recommendations"])


@pytest.mark.parametrize(
    "question",
    [
        "resuma o plano",
        "quais SKUs têm a pior acurácia?",
        "quais clientes estão subestimados?",
        "qual modelo funciona melhor?",
        "quais modelos são campeões com mais frequência?",
        "o que acontece se o preço cair 5%?",
        "quais ajustes pioraram o forecast?",
        "onde estamos abaixo do orçamento?",
        "por que dezembro cresce?",
        "quais os principais riscos?",
        "quais os padrões de demanda das séries?",
        "quanto vendemos este ano?",
        "qual o viés da Vila Verde em dezembro?",
        "e se fizermos uma promoção?",
        "quais clientes têm pior acurácia em julho?",
        "quais produtos estão superestimados em março?",
        "o forecast está superestimado?",
    ],
)
def test_every_intent_answers_in_portuguese(api_client, question):
    r = api_client.post("/api/ai/ask", json={"question": question}).json()
    assert r["meta"]["intent"] is not None, question
    assert r["meta"]["language"] == "pt"
    assert r["answer"], question
    text = " ".join([r["answer"], *r["insights"], *[str(x) for x in (r["chart"] or {}).get("x", [])]])
    assert not ENGLISH_CODES.search(text), (question, ENGLISH_CODES.search(text).group(0))
    assert "Não há resultados de backtest" not in r["answer"], question
    assert not any("Skus" in str(m["label"]) for m in r["metrics"]), question


def test_ambiguous_word_asks_which_member():
    """A word shared by several members gets a clarification, not the generic help."""
    from app.ai import analyst

    members = {"channel": ["Varejo Moderno", "Varejo Tradicional", "E-commerce"], "region": ["Sul"]}
    out = analyst._clarify("como está o varejo?", "pt", members)
    assert out is not None
    assert "Varejo Moderno ou Varejo Tradicional" in out["answer"]
    assert out["recommendations"] == ["Como está o canal Varejo Moderno?", "Como está o canal Varejo Tradicional?"]
    assert analyst._clarify("como está o sul?", "pt", members) is None
