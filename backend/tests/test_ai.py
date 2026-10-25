"""AI Demand Analyst: intent parsing, lever extraction and numeric grounding."""

import pandas as pd
import pytest

from app.ai.intents import detect_language, extract_levers, parse
from app.ai.llm import allowed_numbers, grounding_violations

MEMBERS = {
    "region": ["South", "Southeast"],
    "channel": ["Modern Trade"],
    "customer": ["Atlas Hipermercados", "Vila Verde Mercados"],
    "category": ["Snacks"],
    "brand": ["Crocantes"],
    "sku": ["SKU-20102", "SKU-10101"],
    "product_map": [["SKU-20102", "Crocantes Cheese Chips 90g"]],
}
HORIZON = list(pd.date_range("2026-10-01", periods=12, freq="MS"))
LAST = pd.Timestamp("2026-09-01")


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("What is driving forecast growth in July?", "forecast_drivers"),
        ("Which SKUs have the worst forecast accuracy?", "worst_accuracy"),
        ("Which customers are overforecasted?", "bias_ranking"),
        ("Is December target realistic?", "target_feasibility"),
        ("Which model performs best for SKU-20102?", "best_model"),
        ("What happens if distribution increases by 10%?", "what_if"),
        ("Which commercial overrides reduced accuracy?", "fva_overrides"),
        ("A meta de dezembro é realista?", "target_feasibility"),
        ("Quais clientes estão superestimados?", "bias_ranking"),
        ("Onde estamos abaixo do orçamento?", "budget_gap"),
    ],
)
def test_prd_questions_are_understood(question, intent):
    it = parse(question, MEMBERS, HORIZON, LAST)
    assert it is not None and it.name == intent


def test_entities_months_and_filters():
    it = parse("Which model performs best for SKU-20102?", MEMBERS, HORIZON, LAST)
    assert it.filters == {"sku": "SKU-20102"}
    it = parse("Is December target realistic for Atlas?", MEMBERS, HORIZON, LAST)
    assert it.months == ["2026-12-01"] and it.filters["customer"] == "Atlas Hipermercados"
    it = parse("What is driving forecast growth in July?", MEMBERS, HORIZON, LAST)
    assert it.months == ["2027-07-01"]


def test_lever_extraction_signs():
    assert extract_levers("What happens if distribution increases by 10%?") == {"distribution": 0.10}
    lv = extract_levers("E se o preço cair 5% e a distribuição aumentar 10%?")
    assert lv["price"] == pytest.approx(-0.05) and lv["distribution"] == pytest.approx(0.10)
    lv = extract_levers("reduce price by 3% and raise marketing 20%")
    assert lv["price"] == pytest.approx(-0.03) and lv["marketing"] == pytest.approx(0.20)


def test_language_detection():
    assert detect_language("Is December target realistic?") == "en"
    assert detect_language("A meta de dezembro é realista?") == "pt"


def test_grounding_guard_rejects_invented_numbers():
    facts = {"consensus": 9_828_614.6, "probability": 0.0106, "growth": -0.0102}
    allowed = allowed_numbers(facts)
    assert grounding_violations("Consensus is R$ 9.83M with a 1.1% probability (growth -1.0%).", allowed) == []
    assert grounding_violations("Consensus is R$ 12.4M and growth is 37%.", allowed) == ["12.4", "37"]


def test_unknown_question_returns_none():
    assert parse("hello there", MEMBERS, HORIZON, LAST) is None


def test_analyst_end_to_end(api_client):
    r = api_client.post("/api/ai/ask", json={"question": "Is December target realistic?"}).json()
    assert r["meta"]["intent"]["name"] == "target_feasibility"
    assert r["answer"] and r["metrics"] and r["chart"]["type"] == "bar"
    assert set(r) >= {"answer", "insights", "metrics", "chart", "recommendations", "filters"}
    r = api_client.post("/api/ai/ask", json={"question": "What happens if distribution increases by 10%?"}).json()
    assert r["meta"]["intent"]["levers"] == {"distribution": 0.1}
    assert r["metrics"][1]["value"] > 0
