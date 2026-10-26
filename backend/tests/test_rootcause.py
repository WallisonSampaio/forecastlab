"""Root cause, actions and narrative of the deep dive (spec §4.4, §4.3.3, §4.8) — pure functions.

Cell causes: exclusive priority with direction guards (e = F − A). Plan tags: each rule at its boundary.
Actions: promotion prefill date / uplift clip. Narrative: pt-BR templates and number formatting.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from app.deviations import narrative, rootcause
from app.deviations.rootcause import cell_cause, plan_tags
from app.services import ptbr

H = pd.date_range("2026-10-01", periods=12, freq="MS")


def _cell(**kw):
    """A neutral backtest cell: no driver, small error inside the band."""
    row = {
        "e": 0.0,
        "actual": 100.0,
        "forecast": 100.0,
        "forecast_stat": 100.0,
        "adj": 0.0,
        "stockout": 0.0,
        "promotion": 0.0,
        "merchandising_event": 0.0,
        "distribution": 80.0,
        "distribution_origin": 80.0,
        "price": 10.0,
        "price_ref": 10.0,
        "structural_break": False,
        "break_date": pd.NaT,
        "date": pd.Timestamp("2026-03-01"),
        "ts": 0.0,
        "series_type": "Stable",
        "rmse": 10.0,
    }
    row.update(kw)
    return row


@pytest.fixture
def fake_ctx(monkeypatch):
    prof = pd.DataFrame(
        {"promo_lift": [0.9, 0.02, -0.1, 0.3]},
        index=pd.Index(["A|S1", "B|S2", "C|S3", "D|S4"], name="series_id"),
    )
    monkeypatch.setattr(rootcause, "_profiles", lambda ctx: prof)
    return SimpleNamespace(version="v", run_id="r", future_dates=H)


# ------------------------------------------------------------------------------------------ cell cause
def test_stockout_over_forecast_is_ruptura_even_with_promotion():
    assert cell_cause(_cell(stockout=1, promotion=1, e=30.0), "ac_fc") == "ruptura"


def test_same_row_under_forecast_is_promocao():
    assert cell_cause(_cell(stockout=1, promotion=1, e=-30.0), "ac_fc") == "promocao"


def test_promotion_over_forecast_is_not_promocao():
    assert cell_cause(_cell(promotion=1, e=30.0), "ac_fc") != "promocao"
    assert cell_cause(_cell(merchandising_event=1, e=30.0), "ac_fc") != "merchandising"
    assert cell_cause(_cell(merchandising_event=1, e=-30.0), "ac_fc") == "merchandising"


def test_price_direction_guard():
    # price up 10% -> demand falls -> over-forecast (e > 0) is explained; under-forecast is not
    assert cell_cause(_cell(price=11.0, e=30.0), "ac_fc") == "preco"
    assert cell_cause(_cell(price=11.0, e=-30.0), "ac_fc") != "preco"
    assert cell_cause(_cell(price=9.0, e=-30.0), "ac_fc") == "preco"
    # threshold 5% (inclusive) and never in promotion months
    assert cell_cause(_cell(price=10.5, e=30.0), "ac_fc") == "preco"
    assert cell_cause(_cell(price=10.49, e=30.0), "ac_fc") != "preco"
    assert cell_cause(_cell(price=11.0, e=30.0, promotion=1), "ac_fc") != "preco"


def test_distribution_direction_guard():
    # more distribution -> under-forecast
    assert cell_cause(_cell(distribution=86.0, e=-30.0), "ac_fc") == "distribuicao"
    assert cell_cause(_cell(distribution=86.0, e=30.0), "ac_fc") != "distribuicao"
    assert cell_cause(_cell(distribution=74.0, e=30.0), "ac_fc") == "distribuicao"
    assert cell_cause(_cell(distribution=85.0, e=-30.0), "ac_fc") == "distribuicao"  # 5 p.p. inclusive
    assert cell_cause(_cell(distribution=84.9, e=-30.0), "ac_fc") != "distribuicao"
    assert cell_cause(_cell(distribution=float("nan"), e=-30.0), "ac_fc") != "distribuicao"


def test_patamar_by_tracking_signal_or_recent_break():
    assert cell_cause(_cell(e=30.0, ts=4.5), "ac_fc") == "patamar"
    assert cell_cause(_cell(e=30.0, ts=-4.6), "ac_fc") == "patamar"
    assert cell_cause(_cell(e=30.0, ts=4.4), "ac_fc") != "patamar"
    brk = {"structural_break": True, "e": 30.0}
    assert cell_cause(_cell(**brk, break_date=pd.Timestamp("2025-03-01")), "ac_fc") == "patamar"  # 12 m before
    assert cell_cause(_cell(**brk, break_date=pd.Timestamp("2025-02-01")), "ac_fc") != "patamar"  # 13 m before
    assert cell_cause(_cell(**brk, break_date=pd.Timestamp("2026-04-01")), "ac_fc") != "patamar"  # after t


def test_inherent_and_unexplained():
    assert cell_cause(_cell(e=30.0, series_type="Intermittent"), "ac_fc") == "volatilidade"
    z = rootcause.NOISE_Z * 10.0
    assert cell_cause(_cell(e=z), "ac_fc") == "ruido"
    assert cell_cause(_cell(e=-z), "ac_fc") == "ruido"
    assert cell_cause(_cell(e=z + 0.01), "ac_fc") == "nao_explicado"


def test_ac_cs_adjustment_that_worsened_the_cell():
    # stat 100 (error 0), consensus 120 (error 20) -> worse by more than 0,5% of A
    row = _cell(adj=0.2, forecast=120.0, forecast_stat=100.0, e=20.0, promotion=1)
    assert cell_cause(row, "ac_cs") == "ajuste_piorou"
    # an adjustment that improved the cell is judged by the next rules
    better = _cell(adj=0.2, forecast=120.0, forecast_stat=100.0, actual=125.0, e=-5.0, promotion=1)
    assert cell_cause(better, "ac_cs") != "ajuste_piorou"
    # in ac_cs an adjusted promotion month is no longer "not anticipated"
    assert cell_cause(better, "ac_cs") != "promocao"
    assert cell_cause(_cell(promotion=1, e=-30.0), "ac_cs") == "promocao"
    # ac_fc never yields ajuste_piorou
    assert cell_cause(row, "ac_fc") != "ajuste_piorou"


def test_every_cause_has_label_group_and_action():
    for code, (label, group) in rootcause.CAUSES.items():
        assert label and group in rootcause.GROUP_LABEL
        assert rootcause.recommended_action(code, cause=True, mes="out/2025")["label"]
    assert rootcause.recommended_action("preco", cause=True)["label"] == rootcause.ACTIONS["cause:preco"]
    assert rootcause.recommended_action("preco")["label"] == rootcause.ACTIONS["preco"]
    assert rootcause.recommended_action("promocao", cause=True, mes="nov/2025")["label"] == (
        "Cadastrar a promoção de nov/2025 como ajuste comercial."
    )
    assert "{mes}" not in rootcause.recommended_action("promocao", cause=True)["label"]


def test_cell_evidence_text():
    row = _cell(promotion=1, price=8.8, e=-40.0, hist_adj=0.0)
    assert rootcause.cell_evidence(row) == (
        f"Promoção ativa · sem ajuste registrado · preço {ptbr.pct(-0.12, 1, signed=True)} vs referência · "
        "erro acima de 1,28 × o erro típico"
    )
    assert rootcause.cell_evidence(_cell()) == "Sem fator registrado no mês"
    txt = rootcause.cell_evidence(_cell(distribution=87.0, stockout=1, e=5.0))
    assert txt == "Ruptura no mês · distribuição +7,0 p.p. vs a origem"
    brk = rootcause.cell_evidence(_cell(structural_break=True, break_date=pd.Timestamp("2025-11-01")))
    assert brk == "Mudança de patamar em nov/2025"


# ------------------------------------------------------------------------------------------ plan tags
def _codes(facts, cmp="fc_pl"):
    return [t["code"] for t in plan_tags(facts, cmp)]


def test_growth_premise_boundary():
    base = {"variance": -100.0, "x": 900.0, "p": 1000.0}
    assert _codes({**base, "g_plan": 0.18, "g_fc": 0.10})[0] == "premissa_otimista"  # exactly 0,08
    assert "premissa_otimista" not in _codes({**base, "g_plan": 0.179, "g_fc": 0.10})
    up = {"variance": 100.0, "x": 1100.0, "p": 1000.0}
    assert _codes({**up, "g_plan": 0.02, "g_fc": 0.10})[0] == "momentum_nao_orcado"
    assert "momentum_nao_orcado" not in _codes({**up, "g_plan": 0.021, "g_fc": 0.10})


def test_effect_share_boundary_and_sign():
    base = {"variance": -100.0, "x": 900.0, "p": 1000.0}
    assert _codes({**base, "effects": {"volume": -60.0, "mix": 0.0, "price": -40.0, "events": 0.0}}) == ["preco"]
    assert _codes({**base, "effects": {"volume": -61.0, "mix": 0.0, "price": -39.0, "events": 0.0}}) == ["volume"]
    # same magnitude, opposite sign: does not explain an adverse deviation
    assert "preco" not in _codes({**base, "effects": {"volume": -140.0, "price": 40.0}})
    assert _codes({**base, "effects": {"volume": 0.0, "mix": -50.0, "price": -50.0, "events": 0.0}}) == [
        "preco",
        "mix",
    ]
    assert _codes({**base, "effects": {"events": -45.0, "volume": -55.0}}) == ["evento"]
    tags = plan_tags({"variance": 100.0, "x": 1100.0, "p": 1000.0, "effects": {"mix": 50.0}}, "fc_pl")
    assert tags == [{"code": "mix", "label": "Mix favorável"}]


def test_uncertainty_band_boundaries():
    base = {"variance": -20.0, "x": 980.0, "p": 1000.0, "variance_pct": -0.02}
    assert _codes({**base, "prob_hit": 0.35}) == ["incerteza"]
    assert _codes({**base, "prob_hit": 0.65}) == ["incerteza"]
    assert _codes({**base, "prob_hit": 0.34}) == ["volume"]
    assert _codes({**base, "prob_hit": 0.66}) == ["volume"]
    assert _codes({**base, "prob_hit": 0.5, "variance_pct": -0.05}) == ["volume"]  # |V%| < 5% is strict
    assert _codes({**base, "prob_hit": 0.5}, "ac_pl") == ["volume"]  # fc_* only


def test_challenge_no_budget_structural_and_max_two():
    tg = {"variance": -100.0, "x": 900.0, "p": 1000.0, "challenge": 50.0}
    assert _codes(tg, "fc_tg")[0] == "desafio_comercial"
    assert "desafio_comercial" not in _codes({**tg, "challenge": 49.0}, "fc_tg")
    assert "desafio_comercial" not in _codes(tg, "fc_pl")
    assert _codes({"variance": 50.0, "x": 50.0, "p": 0.0}) == ["sem_orcamento"]
    assert _codes({"variance": -10.0, "x": 90.0, "p": 100.0, "decline_share": 0.30}) == ["queda_estrutural"]
    assert _codes({"variance": -10.0, "x": 90.0, "p": 100.0, "decline_share": 0.29}) == ["volume"]
    assert _codes({"variance": -10.0, "x": 90.0, "p": 100.0, "structural_event": True}) == ["queda_estrutural"]
    many = {
        "variance": -100.0,
        "x": 900.0,
        "p": 1000.0,
        "g_plan": 0.2,
        "g_fc": 0.0,
        "decline_share": 0.5,
        "effects": {"price": -60.0, "mix": -60.0},
    }
    assert _codes(many) == ["premissa_otimista", "queda_estrutural"]
    assert plan_tags({"variance": -1.0}, "fc_pl") == [{"code": "volume", "label": "Volume abaixo do orçado"}]


# ------------------------------------------------------------------------------------------ actions
def test_promo_prefill_date_same_month_next_year_or_first_horizon_month(fake_ctx):
    assert rootcause.promo_prefill_date(fake_ctx, pd.Timestamp("2025-11-01")) == "2026-11-01"
    assert rootcause.promo_prefill_date(fake_ctx, pd.Timestamp("2025-09-01")) == "2026-10-01"  # 2026-09 ∉ H
    assert rootcause.promo_prefill_date(fake_ctx, pd.Timestamp("2026-10-01")) == "2026-10-01"  # 2027-10 ∉ H
    assert rootcause.promo_prefill_date(fake_ctx, None) == "2026-10-01"


def test_promo_uplift_is_clipped_or_defaults(fake_ctx):
    lo, hi = rootcause.PROMO_UPLIFT_CLIP
    assert rootcause.promo_uplift(fake_ctx, "A|S1", "Promoção") == hi
    assert rootcause.promo_uplift(fake_ctx, "B|S2", "Promoção") == lo
    assert rootcause.promo_uplift(fake_ctx, "D|S4", "Promoção") == pytest.approx(0.3)
    assert rootcause.promo_uplift(fake_ctx, "C|S3", "Promoção") == rootcause.DEFAULT_UPLIFT["Promoção"]
    assert rootcause.promo_uplift(fake_ctx, "Z|S9", "Promoção") == rootcause.DEFAULT_UPLIFT["Promoção"]
    assert rootcause.promo_uplift(fake_ctx, "A|S1", "Merchandising") == rootcause.DEFAULT_UPLIFT["Merchandising"]


def test_actions_for_promotion_builds_override_prefill(fake_ctx):
    ent = {
        "cmp": "ac_fc",
        "level": "series",
        "series_id": "A|S1",
        "customer": "A",
        "sku": "S1",
        "date": pd.Timestamp("2025-12-01"),
        "bias": -0.2,
    }
    acts = rootcause.actions_for("promocao", ent, fake_ctx)
    assert [a["kind"] for a in acts] == ["create_override", "ask_ai"]
    pre = acts[0]["prefill"]
    assert pre == {
        "customer": "A",
        "sku": "S1",
        "date": "2026-12-01",
        "event_type": "Promoção",
        "uplift_pct": 0.5,
        "comment": "Sugerido pelo deep dive: promoção não antecipada em dez/2025",
    }
    assert acts[1]["prefill"]["question"] == "Qual o WMAPE de A S1?"
    merch = rootcause.actions_for("merchandising", ent, fake_ctx)[0]["prefill"]
    assert merch["event_type"] == "Merchandising" and merch["uplift_pct"] == 0.12


def test_actions_for_other_codes(fake_ctx):
    ent = {"cmp": "ac_fc", "series_id": "A|S1", "customer": "A", "sku": "S1", "region": "Sul"}
    kinds = {code: [a["kind"] for a in rootcause.actions_for(code, ent, fake_ctx)] for code in rootcause.CAUSES}
    assert kinds["ruptura"][0] == "open_series"
    assert kinds["patamar"][0] == "open_workspace"
    assert kinds["ajuste_piorou"][0] == "open_fva"
    assert kinds["distribuicao"][0] == "simulate"
    assert kinds["volatilidade"] == ["ask_ai"]
    dist = rootcause.actions_for("distribuicao", {**ent, "dist_change": 8.0}, fake_ctx)[0]
    assert dist["prefill"]["distribution_change_pct"] == pytest.approx(0.08)
    # a series is simulated by customer + SKU (spec §4.4), flat keys for ROUTES.cenarios
    assert dist["prefill"]["scope"] == {"customer": "A", "sku": "S1"}
    assert dist["prefill"]["customer"] == "A" and dist["prefill"]["sku"] == "S1" and "region" not in dist["prefill"]
    fva = rootcause.actions_for("ajuste_piorou", ent, fake_ctx)[0]
    assert fva["prefill"]["route"] == "/app/models?tab=fva"
    # plan tags
    plan = {"cmp": "fc_pl", "level": "customer", "member": "A", "customer": "A", "variance": -10.0}
    acts = rootcause.actions_for("premissa_otimista", plan, fake_ctx)
    assert [a["kind"] for a in acts] == ["ask_ai", "simulate"]
    assert acts[0]["prefill"]["question"] == "Como está o cliente A?"
    # the AI filters are the drill path plus the focused member
    ask = rootcause.actions_for("volume", {**plan, "path": {"region": "Sul"}}, fake_ctx)[-1]
    assert ask["kind"] == "ask_ai" and ask["prefill"]["filters"] == {"region": "Sul", "customer": "A"}
    series_ask = rootcause.actions_for("ruido", {**ent, "level": "series", "path": {}}, fake_ctx)[-1]
    assert series_ask["prefill"]["filters"] == {"customer": "A", "sku": "S1"}
    struct = rootcause.actions_for("queda_estrutural", plan, fake_ctx)[0]
    assert struct["prefill"]["event_type"] == "Perda de distribuição" and struct["prefill"]["uplift_pct"] == -0.1
    lever = rootcause.actions_for("desafio_comercial", {**plan, "distribution_change_pct": 0.133}, fake_ctx)[0]
    assert lever["kind"] == "simulate" and lever["prefill"]["distribution_change_pct"] == pytest.approx(0.133)
    # no AI question for model / pattern levels; every label is pt-BR
    assert rootcause.actions_for("volatilidade", {"cmp": "ac_fc", "level": "champion", "member": "ETS"}, fake_ctx) == []
    for a in [*acts, dist, fva, struct, lever]:
        assert a["label"] == rootcause.ACTION_LABEL[a["kind"]]


def test_menu_actions_cover_the_row_menu(fake_ctx):
    """Fixed order (spec §2.3.4 row menu / §2.3.6 drawer bar); the cause's own prefill fills its slot."""
    ent = {
        "cmp": "ac_fc",
        "level": "series",
        "series_id": "A|S1",
        "customer": "A",
        "sku": "S1",
        "date": pd.Timestamp("2025-12-01"),
    }
    menu = list(rootcause.MENU_ORDER)
    for code in ("volatilidade", "ruido", "nao_explicado", "ruptura", "promocao", "preco", None):
        row = [a["kind"] for a in rootcause.menu_actions(code, ent, fake_ctx)]
        assert row == menu, code
        assert [a["label"] for a in rootcause.menu_actions(code, ent, fake_ctx)] == [
            "Abrir ficha",
            "Criar ajuste comercial",
            "Simular cenário",
            "Perguntar à IA",
        ]
    drawer = [a["kind"] for a in rootcause.menu_actions("ruptura", ent, fake_ctx, drawer=True)]
    assert drawer == list(rootcause.DRAWER_ORDER)
    assert [a["kind"] for a in rootcause.menu_actions("patamar", ent, fake_ctx, drawer=True)] == drawer
    # the cause's own prefill fills its slot
    promo = rootcause.menu_actions("promocao", ent, fake_ctx)[1]["prefill"]
    assert promo["event_type"] == "Promoção" and promo["date"] == "2026-12-01" and promo["uplift_pct"] == 0.5
    generic = rootcause.menu_actions("volatilidade", ent, fake_ctx)[1]["prefill"]
    assert generic == {"customer": "A", "sku": "S1", "date": "2026-10-01"}
    dist = rootcause.menu_actions("distribuicao", {**ent, "dist_change": 6.0}, fake_ctx)[2]
    assert dist["kind"] == "simulate" and dist["prefill"]["distribution_change_pct"] == pytest.approx(0.06)
    # a primary action outside the fixed menu is appended
    assert [a["kind"] for a in rootcause.menu_actions("patamar", ent, fake_ctx)] == [*menu, "open_workspace"]
    assert [a["kind"] for a in rootcause.menu_actions("ajuste_piorou", ent, fake_ctx)] == [*menu, "open_fva"]


# ------------------------------------------------------------------------------------------ narrative
def test_plan_headlines():
    f = {
        "node": "Empresa toda",
        "period_phrase": "nos próximos 12 meses",
        "variance": -4.09e6,
        "variance_pct": -0.0416,
        "top": "Litoral Market",
        "top_share": 0.32,
    }
    assert narrative.summary_headline(f, "fc_pl") == (
        f"Empresa toda: consenso {ptbr.money(4.09e6)} abaixo do orçamento ({ptbr.pct(-0.0416, 1, signed=True)}) "
        "nos próximos 12 meses — Litoral Market responde por 32% das perdas."
    )
    up = {**f, "variance": 1e6, "variance_pct": 0.02, "top_fav": "ClickCesta", "top_fav_share": 0.4}
    assert "acima da meta" in narrative.summary_headline(up, "fc_tg")
    assert narrative.summary_headline(up, "fc_tg").endswith("— ClickCesta lidera o ganho (40%).")
    flat = {**f, "variance": -100.0, "variance_pct": -0.004}
    assert narrative.summary_headline(flat, "ac_pl") == (
        "Empresa toda: realizado alinhado ao orçamento nos próximos 12 meses (±0,5%)."
    )
    focus = {
        **f,
        "member": "Litoral Market",
        "variance": -1.58e6,
        "variance_pct": -0.12,
        "tag_label": "Premissa de crescimento otimista",
        "recurrent": True,
        "realized_variance_pct": -0.172,
    }
    assert narrative.focus_headline(focus, "fc_pl") == (
        f"Litoral Market: {ptbr.money(1.58e6)} abaixo do orçamento ({ptbr.pct(-0.12, 1, signed=True)}); "
        "causa principal: premissa de crescimento otimista — já ficou "
        f"{ptbr.pct(-0.172, 1, signed=True)} vs orçamento nos últimos 12 meses."
    )


def test_forecast_headlines_and_diagnosis():
    f = {
        "node": "Empresa toda",
        "period_phrase": "na janela de backtest (out/2025–set/2026)",
        "wmape": 0.148,
        "abs_error": 15.4e6,
        "bias": -0.033,
        "cause1": "Variação normal (dentro da faixa P10–P90)",
        "cause1_share": 0.2,
    }
    h = narrative.summary_headline(f, "ac_fc")
    assert h == (
        "Empresa toda: o forecast estatístico errou 14,8% (R$ 15,40 mi) na janela de backtest "
        "(out/2025–set/2026); variação normal (dentro da faixa P10–P90) explica 20% e o viés é de "
        f"{ptbr.pct(-0.033, 1, signed=True)} (equilibrado)."
    )
    assert "de consenso" in narrative.summary_headline(f, "ac_cs")
    member = narrative.focus_headline({**f, "member": "Litoral Market"}, "ac_fc")
    assert member.startswith("Litoral Market: erro de 14,8% (R$ 15,40 mi) e viés de ")
    assert member.endswith("; causa principal: variação normal (dentro da faixa P10–P90) (20% do erro).")
    assert narrative.summary_headline({**f, "wmape": None}, "ac_fc").startswith("Empresa toda: sem vendas")
    d = narrative.forecast_diagnosis(
        {
            "systematic_share": 0.32,
            "cause1": "Promoção não antecipada",
            "cause1_abs_error": 2.9e6,
            "cause1_n_cells": 247,
            "cause1_direction": "under",
            "fva_pp": 0.0113,
        },
        "ac_cs",
    )
    assert d == [
        "32% do erro é viés sistemático; o restante é ruído que se compensa.",
        "Promoção não antecipada: R$ 2,90 mi de erro em 247 meses-série, quase sempre subestimando.",
        "Ajustes comerciais: 1,1 p.p. de ganho de acurácia.",
    ]
    assert len(narrative.forecast_diagnosis({"systematic_share": 0.5, "fva_pp": 0.01}, "ac_fc")) == 1


def test_plan_diagnosis_order_and_limit():
    facts = {
        "member": "Litoral Market",
        "recurrent": True,
        "realized_variance_pct": -0.172,
        "g_plan": 0.12,
        "g_fc": -0.02,
        "variance": -1.0e6,
        "effects": {"volume": -0.5e6, "mix": -0.1e6, "price": -0.4e6, "events": 0.0},
        "plan_price_premium": 0.0085,
        "events": [{"event_type": "Promoção", "value": 0.1e6, "n": 3}],
    }
    d = narrative.plan_diagnosis(facts, "fc_pl")
    assert len(d) == 3
    assert d[0].startswith("O desvio é recorrente: nos últimos 12 meses Litoral Market já ficou ")
    assert d[1].startswith("O orçamento supõe ")
    assert d[2] == f"O orçamento assume preço {ptbr.pct(0.0085, 1, signed=True)} vs o praticado."
    ac = narrative.plan_diagnosis(
        {
            "g_plan": 0.2,
            "g_fc": 0.15,
            "variance": -3.58e6,
            "effects": {"volume": 3.67e6, "mix": -2.26e6, "price": -5.0e6},
            "reg_price_gap": -0.036,
            "price_promo": -2.24e6,
            "volume_split": {"anticipated": 2.0e6, "surprise": 1.0e6, "uncovered": 0.67e6, "coverage": 0.7},
            "lag_label": "1–3 meses",
        },
        "ac_pl",
    )
    assert ac[0].startswith("O orçamento supunha ") and "o realizado foi" in ac[0]
    assert ac[1].startswith(f"Preço realizado {ptbr.pct(-0.036, 1, signed=True)} vs o orçado nos meses regulares")
    assert ac[2].endswith("foi surpresa de demanda (70% dos meses-série cobertos pelo backtest).")
    assert "já estava no forecast 1–3 meses antes e " in ac[2]
    # the lead time is never hard-coded: without lag_label the clause is dropped
    split = {"volume_split": {"anticipated": 1.0, "surprise": 1.0, "uncovered": 0.0, "coverage": 1.0}}
    (no_lag,) = narrative.plan_diagnosis(split, "ac_pl")
    assert "já estava no forecast e " in no_lag and "meses antes" not in no_lag
    events = narrative.plan_diagnosis(
        {"variance": 1.0, "events": [{"event_type": "Promoção", "value": 5e5, "n": 1}]}, "fc_pl"
    )
    assert events == [f"Eventos comerciais somam +{ptbr.money(5e5)} (1 ajuste; maior: Promoção)."]
    assert narrative.plan_diagnosis({}, "fc_pl") == []
    # plan-engine shape: numeric effects.events + events_list (count and largest type from the list)
    b1 = {
        "variance": -2.0e5,
        "effects": {"volume": -3.0e5, "mix": 0.0, "price": 0.0, "events": 1.0e5},
        "events_list": [
            {"event_type": "Promoção", "value": 0.8e5, "n": 2},
            {"event_type": "Merchandising", "value": 0.2e5, "n": 1},
        ],
    }
    assert narrative.plan_diagnosis(b1, "fc_pl") == [
        f"Eventos comerciais somam +{ptbr.money(1.0e5)} (3 ajustes; maior: Promoção)."
    ]


def test_helpers():
    assert narrative.PP(0.125) == "12,5 p.p."
    assert narrative.Ms(4.2e5).startswith("+R$ ")
    assert narrative.Ms(-4.2e5).startswith("-R$ ")
    assert narrative.lower_first("Variação normal (dentro da faixa P10–P90)").endswith("P10–P90)")
    assert narrative.ai_question("ac_fc", None, None, {"bias": 0.1}) == "Quais clientes estão superestimados?"
    assert narrative.ai_question("ac_fc", "series_type", "Seasonal", {}) is None
