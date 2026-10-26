"""Journey state, forecast trust and cross-endpoint number consistency (spec §4.3.1, §4.3.2, §4.6, §6.1.5)."""

from __future__ import annotations

import dataclasses

import pytest

from app.deviations import common
from app.services import datasets, ptbr, runs, trust
from app.services.context import get_context


@pytest.fixture(scope="module")
def ctx(api_client):
    return get_context()


@pytest.fixture(scope="module")
def trust_payload(api_client):
    r = api_client.get("/api/models/trust")
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------------------------------ /api/journey
def test_journey_without_dataset_is_200(api_client, monkeypatch):
    monkeypatch.setattr(datasets, "active_version", lambda: None)
    r = api_client.get("/api/journey")
    assert r.status_code == 200
    body = r.json()
    assert body["stage"] == "dados" and body["dataset"] is None
    assert body["run"]["state"] == "none" and body["run"]["rerunning"] is False


def test_journey_with_completed_run(api_client, ctx):
    body = api_client.get("/api/journey").json()
    assert body["stage"] == "pronto"
    run, ds = body["run"], body["dataset"]
    assert run["state"] == "completed" and run["run_id"] == ctx.run_id and run["rerunning"] is False
    assert run["finished_at"] and run["duration_s"] > 0 and run["message"].startswith("Concluído")
    assert ds["version"] == ctx.version and ds["n_series"] == len(ctx.series)
    assert ds["has_plan"] is True and ds["plan_derived"] is True  # the fixture's plan is derived
    assert ds["has_overrides_history"] is False
    assert ds["n_months"] == ctx.actuals["date"].dt.to_period("M").nunique()
    assert ds["start_date"] <= ds["end_date"]


def test_journey_rerun_keeps_the_active_run(api_client, ctx, monkeypatch):
    job = {"run_id": "RUN-NOVA", "dataset_version": ctx.version, "status": "running", "progress": 0.42}
    job.update(step="Competição de modelos", done=10, total=40)
    monkeypatch.setattr(runs, "current_job", lambda: job)
    run = api_client.get("/api/journey").json()["run"]
    assert run["state"] == "running" and run["rerunning"] is True
    assert run["run_id"] == ctx.run_id  # the numbers on screen come from the active run
    assert (run["progress"], run["done"], run["total"]) == (0.42, 10, 40)


# ------------------------------------------------------------------------------------------ /api/models/trust
def test_trust_matches_overview_and_fva(api_client, trust_payload):
    t = trust_payload
    assert t["available"] is True
    overview = api_client.get("/api/overview").json()["kpis"]
    fva = api_client.get("/api/fva").json()["stairstep"]
    assert t["accuracy"] == pytest.approx(overview["accuracy"], abs=1e-12)
    assert t["naive_wmape"] == pytest.approx(fva["naive"], abs=1e-12)
    assert t["gain_vs_naive_pp"] == pytest.approx(fva["naive"] - t["wmape"], abs=1e-12)
    # no historical adjustments on the fixture: no consensus FVA
    assert t["consensus_wmape"] is None and t["fva_pp"] is None


def test_trust_shapes(trust_payload, ctx):
    t = trust_payload
    assert sum(t["confidence_revenue_share"].values()) == pytest.approx(1.0, abs=1e-6)
    assert set(t["confidence_series"]) == {"High", "Medium", "Low"}
    assert sum(c["series"] for c in t["champions"]) == t["run"]["n_series"] == len(ctx.series)
    assert [c["series"] for c in t["champions"]] == sorted((c["series"] for c in t["champions"]), reverse=True)
    assert all(c["is_reference"] == (c["model"] == "Naive") for c in t["champions"])
    assert t["run"]["lag_label"] == "1–3 meses"
    assert (t["run"]["n_folds"], t["run"]["fold_horizon"], t["run"]["horizon"]) == (4, 3, 12)
    assert [r["lag"] for r in t["wmape_by_lag"]] == [1, 2, 3]
    assert len(t["backtest_monthly"]) == len(common.backtest_months(ctx))
    assert len(t["caution"]) <= 5
    assert t["pattern_insight"].endswith("cada padrão de demanda tem seu modelo.")
    v = t["verdict"]
    assert v["code"] in ("confiavel", "cautela", "nao_confiavel") and v["label"] == trust.VERDICT_LABEL[v["code"]]
    assert ptbr.pct(t["accuracy"], 1) in v["headline"]


def test_trust_backtest_monthly_is_the_champion_revenue(trust_payload, ctx):
    from app.deviations import forecast_error

    cells = forecast_error.error_cells(ctx, "ac_fc", ctx.series["series_id"], common.backtest_months(ctx))
    assert sum(r["actual"] for r in trust_payload["backtest_monthly"]) == pytest.approx(cells["actual_rev"].sum())
    assert sum(r["statistical"] for r in trust_payload["backtest_monthly"]) == pytest.approx(
        cells["forecast_rev"].sum()
    )


def test_trust_without_run(ctx):
    assert trust.trust(dataclasses.replace(ctx, run_id=None)) == {"available": False, "reason": trust.NO_RUN}


@pytest.mark.parametrize(
    ("accuracy", "bias", "low", "gain", "code"),
    [
        (0.80, 0.05, 0.20, 0.001, "confiavel"),  # every boundary inclusive
        (0.7999, 0.0, 0.0, 0.10, "cautela"),  # accuracy just below 80%
        (0.65, -0.10, 0.90, 0.01, "cautela"),  # cautela boundaries; low share does not matter
        (0.95, 0.0, 0.0, 0.0, "nao_confiavel"),  # no gain over the naive method
    ],
)
def test_verdict_boundaries(accuracy, bias, low, gain, code):
    assert trust.verdict_code(accuracy, bias, low, gain) == code


def test_verdict_reasons_one_per_failed_condition():
    assert trust.verdict_reasons(0.9, 0.01, 0.1, 0.05, 0.3, 0.1) == []
    reasons = trust.verdict_reasons(0.7, 0.072, 0.26, -0.01, 0.25, 0.30)
    assert len(reasons) == 4
    assert "Viés de +7,2%: o forecast superestima a demanda." in reasons
    assert "A receita em séries de confiança baixa é de 26%." in reasons


def test_verdict_headline_templates():
    ok = trust.verdict_headline(0.852, 0.125, 0.69, 0.273)
    assert ok == (
        "O forecast acerta 85,2% fora da amostra, erra 12,5 p.p. menos que o método ingênuo e 69% da receita "
        "prevista vem de séries com confiança alta."
    )
    bad = trust.verdict_headline(0.70, -0.02, 0.5, 0.28)
    assert "não supera o método ingênuo (72,0%)" in bad


def test_pattern_insight_uses_the_plural():
    rows = [
        {
            "series_type": "Seasonal",
            "label": "Sazonal",
            "n": 66,
            "top_model": "Regression",
            "top_model_label": "Regressão",
            "top_model_series": 31,
        }
    ]
    assert (
        trust.pattern_insight(rows)
        == "Nas 66 séries sazonais, Regressão venceu 31 — cada padrão de demanda tem seu modelo."
    )


def test_lag_label_is_computed():
    assert common.lag_label(1) == "1 mês" and common.lag_label(3) == "1–3 meses"


# ------------------------------------------------------------------------------------------ §6.1.5
def test_cross_endpoint_number_consistency(api_client, trust_payload):
    story = api_client.get("/api/story").json()
    ch = {c["id"]: c for c in story["chapters"]}
    cockpit = api_client.get("/api/sop/cockpit").json()["kpis"]
    feas = api_client.get("/api/sop/feasibility").json()
    fva = api_client.get("/api/fva").json()["stairstep"]

    assert ch["projecao"]["facts"]["fc"] == pytest.approx(cockpit["consensus"], rel=1e-12)
    assert ch["meta"]["facts"]["prob"] == pytest.approx(feas["probability"], abs=1e-12)
    assert trust_payload["wmape"] == pytest.approx(fva["statistical"], abs=1e-12)

    ac_fc = api_client.get("/api/deviations/summary", params={"cmp": "ac_fc"}).json()
    assert ac_fc["kpis"][0]["id"] == "accuracy"
    assert ac_fc["kpis"][0]["value"] == pytest.approx(1 - trust_payload["wmape"], abs=1e-9)

    fc_pl = api_client.get("/api/deviations/summary", params={"cmp": "fc_pl"}).json()
    v = fc_pl["kpis"][0]["value"]
    assert v == pytest.approx(cockpit["gap_vs_budget"], rel=1e-9)
    # the report and the deep dive print the same number
    assert ch["resumo"]["facts"]["gap_pl"] == pytest.approx(v, rel=1e-12)
    assert ptbr.money(abs(v)) in ch["projecao"]["headline"]
    assert ch["precisao"]["facts"]["wmape"] == pytest.approx(trust_payload["wmape"], abs=1e-12)
