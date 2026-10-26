"""Executive story (GET /api/story, spec §4.5, §4.8): chapters, templates, decisions, AI questions and export."""

from __future__ import annotations

import dataclasses
import html
import json
import re
from typing import Any

import pytest

from app.ai.analyst import _members
from app.ai.intents import parse
from app.api.deps import ctx_dep
from app.main import app
from app.services import ptbr
from app.services.context import clean, get_context
from app.story import decisions as D
from app.story import templates as T
from app.story.builder import VARIANCE_BARS, build_story

ORDER = ["resumo", "realizado", "precisao", "projecao", "gap", "meta", "decisoes"]
KIND = {
    "resumo": "kpis",
    "realizado": "bridge",
    "precisao": "cause_bars",
    "projecao": "monthly_variance",
    "gap": "variance_bars",
    "meta": "feasibility_range",
    "decisoes": "decision_table",
}
ENGLISH = re.compile(r"\b(budget|target|revenue|balanced|over|under|none|nan)\b", re.IGNORECASE)
TEXT_KEYS = {
    "label",
    "headline",
    "reason",
    "notice",
    "notices",
    "hint",
    "text",
    "delta",
    "note",
    "level_label",
    "group_label",
    "title",
    "short",
    "question",
    "context",
    "governing_thought",
    "situacao",
    "complicacao",
    "resposta",
    "decision",
    "evidence",
    "owner",
    "scope_label",
    "horizon_label",
    "ltm_label",
    "backtest_label",
}
# Probed "Perguntar à IA" questions and the intent each one reaches (spec §2.2.3, §4.3.3).
INTENT = {
    "resumo": "risks",
    "realizado": "forecast_value",
    "precisao": ("fva_overrides", "bias_ranking"),
    "projecao": "budget_gap",
    "gap": "entity_overview",
    "meta": "target_feasibility",
}
FIXED_QUESTIONS = {
    "resumo": {T.ASK_RESUMO},
    "realizado": {T.ASK_REALIZADO},
    "precisao": {T.ASK_PRECISAO_FVA, T.ASK_PRECISAO_OVER, T.ASK_PRECISAO_UNDER},
    "meta": {T.ASK_META},
}
PATTERN_QUESTIONS = {
    "projecao": re.compile(r"^Por que o forecast de [a-zç]+ de \d{4} está (abaixo|acima) do orçamento\?$"),
    "gap": re.compile(r"^Como está (o cliente|a categoria|o SKU) .+\?$"),
}


def _texts(payload: Any) -> list[str]:
    out: list[str] = []
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k in TEXT_KEYS:
                out += [s for s in (v if isinstance(v, list) else [v]) if isinstance(s, str)]
            if isinstance(v, dict | list):
                out += _texts(v)
    elif isinstance(payload, list):
        for v in payload:
            out += _texts(v)
    return out


@pytest.fixture(scope="module")
def ctx(api_client):
    return get_context()


@pytest.fixture(scope="module")
def story(api_client) -> dict[str, Any]:
    r = api_client.get("/api/story")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["available"] is True
    return body


@pytest.fixture(scope="module")
def chapters(story) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in story["chapters"]}


@pytest.fixture(scope="module")
def no_plan_story(api_client, ctx) -> dict[str, Any]:
    """The same base without any plan row (a new context object, so no cache is shared)."""
    bare = dataclasses.replace(ctx, plan=ctx.plan.iloc[0:0])
    app.dependency_overrides[ctx_dep] = lambda: bare
    try:
        r = api_client.get("/api/story")
    finally:
        app.dependency_overrides.pop(ctx_dep, None)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------------------------------ contract
def test_seven_chapters_in_order(story):
    assert [c["id"] for c in story["chapters"]] == ORDER
    assert [c["index"] for c in story["chapters"]] == list(range(1, 8))
    ref = story["reference"]
    assert ref["plan_derived"] is True and ref["has_plan"] is True
    assert ref["horizon_months"] == 12 and ref["lag_label"] == "1–3 meses" and ref["scope_label"] == "Empresa toda"
    assert set(story["scqa"]) == {"situacao", "complicacao", "resposta"}
    assert story["governing_thought"] == story["chapters"][0]["headline"]


def test_ok_chapters_follow_the_copy_rules(story):
    for ch in story["chapters"]:
        assert ch["visual"]["kind"] == KIND[ch["id"]]
        assert len(ch["takeaways"]) <= 3
        if ch["status"] != "ok":
            continue
        h = ch["headline"]
        assert 1 <= len(h) <= T.MAX_HEADLINE_CHARS, h
        if not (ch["id"] == "decisoes" and ch["facts"]["n"] == 0):
            assert "R$" in h or "%" in h, h
        for t in ch["takeaways"]:
            assert t["text"].count("**") % 2 == 0, t["text"]
        if ch["id"] != "decisoes":
            assert ch["investigate"]["params"]["cmp"], ch["id"]
        assert all(isinstance(v, int | float | str) or v is None for v in ch["facts"].values()), ch["id"]


def test_no_placeholder_or_english_in_text(story):
    texts = _texts(story)
    assert texts
    assert not [s for s in texts if ptbr.NA in s], "n/d inside a sentence"
    assert not [s for s in texts if ENGLISH.search(s)]


def test_resumo_kpis_and_scqa(chapters, story):
    cards = chapters["resumo"]["visual"]["data"]["cards"]
    assert len(cards) == 4
    assert [c["id"] for c in cards] == ["actual_ltm", "consensus", "prob_target", "accuracy"]
    assert chapters["resumo"]["takeaways"] == []
    f = chapters["resumo"]["facts"]
    assert T.M(f["fc"]) in story["scqa"]["complicacao"]
    assert T.M(f["ac_ltm"]) in story["scqa"]["situacao"]


def test_headlines_print_the_facts(chapters, api_client):
    cockpit = api_client.get("/api/sop/cockpit").json()["kpis"]
    p = chapters["projecao"]
    assert ptbr.money(cockpit["consensus"]) in p["headline"]
    assert T.M(p["facts"]["gap_pl"]) in p["headline"] and T.P1s(p["facts"]["fc_vs_ltm"]) in p["headline"]
    r = chapters["realizado"]
    assert T.M(r["facts"]["v"]) in r["headline"]
    pr = chapters["precisao"]
    assert T.P1(pr["facts"]["wmape"]) in pr["headline"]
    m = chapters["meta"]
    assert T.M(m["facts"]["target"]) in m["headline"] and T.P0(m["facts"]["prob"]) in m["headline"]
    feas = api_client.get("/api/sop/feasibility").json()
    assert m["facts"]["prob"] == pytest.approx(feas["probability"], abs=1e-12)
    assert m["visual"]["data"]["probability"] == pytest.approx(feas["probability"], abs=1e-12)
    assert "emoji" not in m["visual"]["data"]["display"]


def test_precisao_without_overrides_history(chapters):
    t = [x["text"] for x in chapters["precisao"]["takeaways"]]
    assert "Sem histórico de ajustes comerciais para medir o valor agregado." in t
    assert chapters["precisao"]["ask_ai"] in (T.ASK_PRECISAO_OVER, T.ASK_PRECISAO_UNDER)


def test_bridge_and_variance_visuals(chapters):
    steps = chapters["realizado"]["visual"]["data"]["steps"]
    assert [s["key"] for s in steps] == ["reference", "volume", "mix", "price", "compared"]
    total = steps[0]["value"] + sum(s["value"] for s in steps[1:-1])
    assert total == pytest.approx(steps[-1]["value"], rel=1e-9)
    data = chapters["gap"]["visual"]["data"]
    assert len(data["rows"]) <= VARIANCE_BARS and data["level"] == "customer"
    shown = sum(r["variance"] for r in data["rows"]) + (data["others"]["value"] if data["others"] else 0.0)
    assert shown == pytest.approx(chapters["gap"]["facts"]["v"], rel=1e-9, abs=1e-6)


# ------------------------------------------------------------------------------------------ decisions
def test_decisions(chapters):
    dec = chapters["decisoes"]
    rows = dec["visual"]["data"]["rows"]
    assert len(rows) <= D.MAX_DECISIONS
    assert len({r["code"] for r in rows}) == len(rows)
    assert [r["impact"] for r in rows] == sorted((r["impact"] for r in rows), reverse=True)
    for r in rows:
        assert r["code"] in D.DECISION_CODES and r["short"] and r["impact_basis"] in D.IMPACT_BASIS
        assert r["impact"] > 0 and r["link"]["route"].startswith("/app/")
    if len(rows) >= 2:  # impacts overlap: never summed
        assert ptbr.money(sum(r["impact"] for r in rows)) not in dec["headline"]
        assert T.M(rows[0]["impact"]) in dec["headline"]
    assert dec["ask_ai"] is None


def test_decision_rules_on_synthetic_facts(ctx):
    rows = [
        {
            "label": "A",
            "key": "A",
            "variance": -300.0,
            "tags": [{"code": "premissa_otimista"}],
            "growth_plan": 0.2,
            "growth_fc": -0.03,
            "realized_variance_pct": -0.17,
        },
        {"label": "B", "key": "B", "variance": 100.0, "tags": [{"code": "volume"}]},
    ]
    facts = {
        "level": "customer",
        "meta_level": "region",
        "scope_path": {},
        "gap_rows": rows,
        "p_node": 10_000.0,
        "price_effect": -200.0,
        "plan_price_premium": 0.01,
        "reg_price_gap": -0.036,
        "causes": [
            {"code": "promocao", "share": 0.19, "abs_error": 190.0},
            {"code": "merchandising", "share": 0.06, "abs_error": 60.0},
        ],
        "assess": {
            "available": True,
            "classification": "STRETCH",
            "probability": 0.29,
            "target": 1500.0,
            "consensus": 1000.0,
        },
        "lever_text": "+13,3% de distribuição numérica",
        "simulate_route": "/app/scenarios?distribution_change_pct=0.133",
        "fva": {},
        "ids": None,
        "series_revenue": None,
        "annualise": 1.0,
    }
    out = {r["code"]: r for r in D.build_decisions(ctx, {}, facts)}
    assert set(out) == {"D1", "D2", "D3", "D4", "D7"}
    assert out["D4"]["impact"] == 500.0 and out["D4"]["link"]["route"] == facts["simulate_route"]
    assert out["D1"]["short"] == "revisar o orçamento de 1 cliente" and "-17,0%" in out["D1"]["evidence"]
    assert out["D2"]["impact"] == pytest.approx(250.0) and out["D2"]["impact_basis"] == "backtest_anualizado"
    assert out["D2"]["link"]["route"] == "/app/desvios?lente=previsao&cmp=ac_fc&nivel=customer&causa=promocao"
    assert out["D7"]["link"]["route"] == "/app/desvios?nivel=category"
    facts["assess"] = {**facts["assess"], "classification": "UNDERESTIMATED", "target": 900.0}
    assert {r["code"] for r in D.build_decisions(ctx, {}, facts)} >= {"D8"}


# ------------------------------------------------------------------------------------------ AI questions
def test_ask_ai_questions_are_probed(ctx, story):
    members = _members(ctx)
    for ch in story["chapters"]:
        q = ch["ask_ai"]
        if ch["id"] == "decisoes":
            assert q is None
            continue
        assert q, ch["id"]
        if ch["id"] in FIXED_QUESTIONS:
            assert q in FIXED_QUESTIONS[ch["id"]], q
        else:
            assert PATTERN_QUESTIONS[ch["id"]].match(q), q
        intent = parse(q, members, list(ctx.future_dates), ctx.last_actual)
        expected = INTENT[ch["id"]]
        assert intent is not None and intent.name in (expected if isinstance(expected, tuple) else (expected,)), (
            q,
            intent and intent.name,
        )


# ------------------------------------------------------------------------------------------ scope and no plan
def test_story_by_region(api_client, ctx):
    region = str(ctx.series["region"].iloc[0])
    body = api_client.get("/api/story", params={"region": region}).json()
    assert body["available"] and body["reference"]["scope_label"] == region
    assert [c["id"] for c in body["chapters"]] == ORDER
    assert body["chapters"][5]["investigate"]["params"]["nivel"] != "region"


def test_story_without_plan(no_plan_story):
    s = no_plan_story
    ch = {c["id"]: c for c in s["chapters"]}
    assert [c["id"] for c in s["chapters"]] == ORDER and s["reference"]["has_plan"] is False
    for cid in ("realizado", "gap", "meta"):
        assert ch[cid]["status"] == "empty" and ch[cid]["notice"] == T.NOTICE_NO_PLAN
        assert ch[cid]["investigate"] is None and ch[cid]["takeaways"] == [] and ch[cid]["headline"] == ch[cid]["title"]
    assert "não tem orçamento nem meta" in s["governing_thought"]
    assert "faixa provável" in ch["projecao"]["headline"]
    assert ch["projecao"]["visual"]["data"]["p_label"] == "Ano anterior"
    cards = ch["resumo"]["visual"]["data"]["cards"]
    assert len(cards) == 4 and cards[2]["label"] == "Faixa provável (P10–P90)"
    assert "orçamento" not in s["scqa"]["situacao"]
    assert not [t for t in _texts(s) if ptbr.NA in t]


def test_story_without_run(ctx):
    assert build_story(dataclasses.replace(ctx, run_id=None)) == {
        "available": False,
        "reason": "Ainda não há uma execução de forecast concluída.",
    }


# ------------------------------------------------------------------------------------------ templates
def test_realizado_headline_variants():
    base = {"v": -3_580_000.0, "v_pct": -0.039, "vol": 3_670_000.0, "mix": -2_260_000.0, "price": -5_000_000.0}
    h = T.realizado_headline({**base, "units_pct": 0.040})
    assert h == (
        "Vendemos 4,0% mais unidades que o orçado, mas a receita ficou 3,9% abaixo do orçamento (R$ 3,58 mi): "
        "preço (-R$ 5,00 mi) e mix (-R$ 2,26 mi) anularam o ganho de volume."
    )
    h = T.realizado_headline(
        {"v": -1e6, "v_pct": -0.05, "vol": -0.8e6, "mix": -0.1e6, "price": -0.1e6, "units_pct": -0.04}
    )
    assert h.endswith("volume explica 80% do desvio.")
    h = T.realizado_headline({"v": 1e6, "v_pct": 0.05, "vol": 0.7e6, "mix": 0.2e6, "price": 0.1e6})
    assert h == "Superamos o orçamento dos últimos 12 meses em R$ 1,00 mi (+5,0%), puxados por volume (+R$ 700,0 mil)."


def test_governing_thought_demo_example():
    f = {
        "has_plan": True,
        "fc_vs_ltm": 0.073,
        "gap_pl": -4_090_000.0,
        "gap_pl_pct": -0.042,
        "n_top": 2,
        "share_top": 0.60,
        "level": "customer",
        "prob_tg": 0.29,
    }
    assert T.governing_thought(f, 12) == (
        "Vamos crescer 7,3% nos próximos 12 meses, mas fechar R$ 4,09 mi abaixo do orçamento: 2 clientes "
        "concentram 60% das perdas e a meta tem 29% de chance."
    )


def test_governing_thought_when_the_consensus_falls():
    f = {"has_plan": True, "fc_vs_ltm": -0.037, "gap_pl": -1.58e6, "gap_pl_pct": -0.22, "prob_tg": 0.09}
    assert T.governing_thought(f, 12) == (
        "Vamos recuar 3,7% nos próximos 12 meses e fechar R$ 1,58 mi abaixo do orçamento; a meta tem 9% de chance."
    )


def test_projecao_worst_month_outside_the_worst_quarter():
    f = {
        "has_plan": True,
        "worst_q": "T1 · out–dez/2026",
        "worst_q_gap": -341_300.0,
        "worst_q_start": "2026-10-01",
        "worst_q_end": "2026-12-01",
        "worst_month": "2027-02-01",
        "worst_month_gap": -346_200.0,
    }
    first = T.projecao_takeaways(f)[0]["text"]
    assert (
        first
        == "**T1 · out–dez/2026** é o trimestre mais crítico (-R$ 341,3 mil); o pior mês é **fev/2027** (-R$ 346,2 mil)."
    )
    inside = T.projecao_takeaways({**f, "worst_month": "2026-12-01"})[0]["text"]
    assert inside.endswith("**dez/2026** sozinho responde por -R$ 346,2 mil.")


def test_meta_takeaways_do_not_repeat_the_growth_reason():
    f = {"required_growth": 0.294, "forecast_growth": -0.037, "historical_growth": 0.085, "r1": "Nordeste"}
    reasons = [
        "O crescimento necessário de +29,4% está muito acima do crescimento histórico de +8,5%",
        "A meta está acima do consenso (P50), mas dentro da faixa P10-P90",
    ]
    texts = [t["text"] for t in T.meta_takeaways({**f, "p1": 0.09, "n_by": 1}, reasons)]
    assert texts == [
        "A meta está acima do consenso (P50), mas dentro da faixa P10–P90.",
        "Crescimento exigido **+29,4%** vs previsto -3,7% e histórico +8,5%.",
    ]  # one region only: no "menor chance por região"
    texts = [t["text"] for t in T.meta_takeaways({**f, "p1": 0.09, "n_by": 5, "n_aggr": 1}, reasons[:1])]
    assert texts[-1] == "Menor chance por região: **Nordeste** (9%); 1 região com meta agressiva."


def test_takeaway_links_select_the_member_key():
    f = {"v": -1.0, "n1": "Cliente · SKU-1 Produto", "key1": "Cliente|SKU-1", "p_top1": 0.2, "rv_top1": None}
    link = T.gap_takeaways(f, "series")[-1]["link"]
    assert link["params"]["sel"] == "Cliente|SKU-1"
    r = {"top_adv": "Cliente · SKU-1 Produto", "top_adv_key": "Cliente|SKU-1", "top_adv_share": 1.0, "top_adv_v": -1.0}
    assert T.realizado_takeaways(r, "series")[-1]["link"]["params"]["sel"] == "Cliente|SKU-1"


def test_gap_headline_fits_two_lines():
    long_name = "Rede Nacional de Supermercados e Atacarejos do Brasil Central e Litoral Sul Ltda"
    f = {
        "v": -1e6,
        "level": "customer",
        "n_top": 2,
        "share": 0.6,
        "n1": long_name,
        "n2": long_name,
        "tag1_code": "premissa_otimista",
        "tag2_code": "premissa_otimista",
        "gp1": 0.2,
        "gp2": 0.2,
        "gf1": 0.0,
        "gf2": 0.0,
    }
    h = T.gap_headline(f)
    assert h.startswith("2 clientes concentram 60% das perdas vs orçamento")
    assert len(T.gap_headline({**f, "n1": "A", "n2": "B"})) <= T.MAX_HEADLINE_CHARS


def test_lever_choice_is_normalised():
    levers = [
        {"lever": "Price", "required_change": -0.076, "plausible": True},
        {"lever": "Distribution", "required_change": 0.133, "plausible": True},  # 0,133 / 0,20 = 0,67
        {"lever": "Promotions", "required_change": 3.0, "plausible": True},  # 3 / (12/3) = 0,75
        {"lever": "Marketing", "required_change": 4.93, "plausible": False},
    ]
    best = T.pick_lever(levers, 12)
    assert best["lever"] == "Distribution"
    assert T.lever_text("Distribution", 0.133) == "+13,3% de distribuição numérica"
    assert T.lever_text("Promotions", 2.2) == "3 meses de promoção"
    assert T.lever_text(None, None) == "mais de uma alavanca combinada"
    assert T.pick_lever([levers[0]], 12) is None  # price is never a revenue lever


def test_routes_match_the_frontend_builders():
    assert T.deviations_href({"cmp": "fc_pl", "periodo": "h", "nivel": "region"}) == "/app/desvios"
    assert (
        T.deviations_href({"cmp": "fc_pl", "periodo": "h", "nivel": "customer", "sel": "Litoral Market"})
        == "/app/desvios?nivel=customer&sel=Litoral%20Market"
    )
    assert T.deviations_href({"cmp": "ac_fc", "nivel": "series", "path": {"region": "Sul"}}) == (
        "/app/desvios?lente=previsao&cmp=ac_fc&region=Sul&nivel=series"
    )
    assert T.scenarios_route({"region": "Sul"}, {"distribution_change_pct": 0.13266}) == (
        "/app/scenarios?region=Sul&distribution_change_pct=0.133"
    )


# ------------------------------------------------------------------------------------------ export
def test_export_html_is_the_story(api_client, story):
    r = api_client.get("/api/export/executive-html", params={"download": "true"})
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    page = r.text
    for ch in story["chapters"]:
        assert html.escape(ch["headline"]) in page, ch["id"]
    assert page.count(html.escape(story["governing_thought"])) == 1  # chapter 1's headline, printed once
    assert html.escape(story["scqa"]["situacao"]) in page
    assert "P10–P90 do consenso" in page and "(estatística)" not in page  # journey band = consensus band
    assert 'lang="pt-BR"' in page and "<svg" in page and "Relatório Executivo de S&amp;OP" in page
    assert "Desenvolvido por Wallison Sampaio · Especialista em Inteligência Comercial" in page
    assert "<strong>" in page and "**" not in page


def test_export_prints_empty_chapter_notices(ctx):
    from app.exports.html_report import build_html

    page = build_html(dataclasses.replace(ctx, plan=ctx.plan.iloc[0:0]))
    assert html.escape(T.NOTICE_NO_PLAN) in page and page.count("Capítulo ") == 7


def test_story_is_json_safe_and_cached(ctx):
    a = build_story(ctx, {})
    b = build_story(ctx, {})
    assert a is not b and a["chapters"] is not b["chapters"]
    assert json.dumps(clean(a), sort_keys=True) == json.dumps(clean(b), sort_keys=True)
