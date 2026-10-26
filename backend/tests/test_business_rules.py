"""S&OP business rules: scenarios, target feasibility, FVA, allocation, hierarchy, overrides."""

import numpy as np
import pandas as pd
import pytest

from app.fva.fva import evaluate_override
from app.reconciliation.hierarchy import BottomUp, TopDownHistoricalProportions
from app.sop.feasibility import classify


def test_fva_override_example_from_prd():
    r = evaluate_override(statistical=100, override_pct=0.20, actual=103)
    assert r["consensus"] == pytest.approx(120)
    assert r["outcome"] == "Worsened"
    assert r["message"] == "O ajuste reduziu a acurácia do forecast."
    good = evaluate_override(statistical=100, override_pct=0.20, actual=118)
    assert good["outcome"] == "Improved" and good["fva_units"] == pytest.approx(16)
    assert good["message"] == "O ajuste melhorou a acurácia do forecast."
    neutral = evaluate_override(statistical=100, override_pct=0.0, actual=103)
    assert neutral["outcome"] == "Neutral"
    assert neutral["message"] == "O ajuste não teve efeito relevante na acurácia."


def test_feasibility_texts_are_portuguese():
    from app.sop.feasibility import CLASSES, _recommendation

    assert [c["label"] for c in CLASSES.values()] == ["Realista", "Desafiadora", "Agressiva", "Subestimada"]
    txt = _recommendation("AGGRESSIVE", 1_930_000, 0.148, "revenue")
    assert "+14,8%" in txt and "R$ 1,93 mi" in txt
    assert "1.234 unidades" in _recommendation("STRETCH", 1234, 0.05, "units")


def test_event_library_uses_shared_portuguese_types():
    from app.services.overrides import EVENT_LIBRARY

    assert [e["type"] for e in EVENT_LIBRARY] == [
        "Promoção",
        "Merchandising",
        "Ganho de distribuição",
        "Perda de distribuição",
        "Nova loja",
        "Ganho de cliente",
        "Perda de cliente",
        "Campanha",
        "Mudança de preço",
        "Lançamento",
        "Deslistagem",
        "Ação de concorrente",
    ]
    assert all(e["description"] for e in EVENT_LIBRARY)


@pytest.mark.parametrize(
    ("target", "expected"),
    [(80, "UNDERESTIMATED"), (98, "REALISTIC"), (106, "STRETCH"), (125, "AGGRESSIVE")],
)
def test_target_classification(target, expected):
    mean, sigma = 100.0, 8.0
    cls, prob = classify(target, mean, sigma, mean - 1.2816 * sigma, mean + 1.2816 * sigma)
    assert cls == expected
    assert 0 <= prob <= 1


def test_bottom_up_is_coherent_and_top_down_preserves_total():
    base = pd.DataFrame({"region": ["S", "S", "N", "N"], "date": ["m1", "m2", "m1", "m2"], "value": [10, 20, 5, 5]})
    hist = pd.DataFrame({"region": ["S", "N"], "date": pd.to_datetime(["2024-01-01", "2024-01-01"]), "value": [3, 1]})
    bu = BottomUp().reconcile(base, hist, "region")
    assert bu["value"].sum() == base["value"].sum()
    td = TopDownHistoricalProportions().reconcile(base, hist, "region")
    assert td["value"].sum() == pytest.approx(base["value"].sum())
    assert td.groupby("region")["value"].sum()["S"] == pytest.approx(30)


@pytest.fixture
def ctx(api_client):
    from app.services.context import get_context

    return get_context()


def test_scenario_distribution_uplift_matches_elasticity(ctx):
    from app.scenarios.elasticity import estimate_elasticities, for_category
    from app.scenarios.engine import ScenarioParams, simulate_rows

    rows = simulate_rows(ctx, ScenarioParams(distribution_change_pct=0.10))
    el = estimate_elasticities(ctx.version)
    last_dist = ctx.actuals.sort_values("date").groupby("series_id")["distribution"].last()
    r = rows.iloc[0]
    d0 = last_dist[r["series_id"]]
    expected = (min(100.0, d0 * 1.1) / d0) ** for_category(el, r["category"])["distribution_elasticity"]
    assert r["scenario_units"] / r["base_units"] == pytest.approx(expected)
    noop = simulate_rows(ctx, ScenarioParams())
    np.testing.assert_allclose(noop["scenario_units"], noop["base_units"])


def test_promotion_months_only_affect_selected_months(ctx):
    from app.scenarios.engine import ScenarioParams, simulate_rows

    month = ctx.future_dates[2].strftime("%Y-%m-01")
    rows = simulate_rows(ctx, ScenarioParams(promo_months=[month]))
    on = rows["date"] == ctx.future_dates[2]
    assert (rows.loc[on, "scenario_units"] >= rows.loc[on, "base_units"]).all()
    np.testing.assert_allclose(rows.loc[~on, "scenario_units"], rows.loc[~on, "base_units"])


def test_allocation_sums_to_total(ctx):
    from app.sop.allocation import allocate

    for method in ("historical", "potential", "forecast", "strategic"):
        out = allocate(ctx, "customer", method, total_target=1_000_000, measure="revenue")
        assert sum(r["allocated_target"] for r in out["rows"]) == pytest.approx(1_000_000)
        assert sum(r["weight"] for r in out["rows"]) == pytest.approx(1.0)


def test_override_moves_consensus_by_uplift(api_client, ctx):
    sid = ctx.series["series_id"].iloc[0]
    cust, sku = sid.split("|")
    month = ctx.future_dates[1]
    base = ctx.forecast.loc[(ctx.forecast["series_id"] == sid) & (ctx.forecast["date"] == month), "p50"].item()
    r = api_client.post(
        "/api/overrides",
        json={
            "customer": cust,
            "sku": sku,
            "date": str(month.date()),
            "event_type": "Promoção",
            "uplift_pct": 0.15,
            "comment": "teste",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["event_type"] == "Promoção" and r.json()["created_by"] == "Planejador de Demanda"
    from app.services.context import get_context

    f = get_context().forecast
    cons = f.loc[(f["series_id"] == sid) & (f["date"] == month), "consensus"].item()
    assert cons == pytest.approx(base * 1.15)
    api_client.delete(f"/api/overrides/{r.json()['override_id']}")
    f = get_context().forecast
    assert f.loc[(f["series_id"] == sid) & (f["date"] == month), "consensus"].item() == pytest.approx(base)


def test_override_validation_messages_are_portuguese(api_client, ctx):
    month = str(ctx.future_dates[0].date())
    r = api_client.post("/api/overrides", json={"date": month, "event_type": "Festa", "uplift_pct": 0.1})
    assert r.status_code == 400 and r.json()["detail"].startswith("Tipo de evento inválido")
    r = api_client.post("/api/overrides", json={"date": month, "event_type": "Campanha", "uplift_pct": 9})
    assert r.status_code == 400 and r.json()["detail"] == "O ajuste deve ficar entre -100% e +500%"
    r = api_client.post("/api/overrides", json={"date": "2001-01-01", "event_type": "Campanha", "uplift_pct": 0.1})
    assert r.status_code == 400 and "horizonte do forecast" in r.json()["detail"]
    assert api_client.delete("/api/overrides/OVR-NAOEXISTE").json()["detail"] == "Ajuste comercial não encontrado"


def test_legacy_english_overrides_still_display(api_client, ctx):
    """Overrides saved by the English version keep working and are shown with Portuguese labels."""
    from app import db
    from app.services import context

    sid = ctx.series["series_id"].iloc[0]
    cust, sku = sid.split("|")
    legacy = pd.DataFrame(
        [
            {
                "override_id": "OVR-LEGACY01",
                "dataset_version": ctx.version,
                "customer": cust,
                "sku": sku,
                "date": ctx.future_dates[2],
                "event_type": "Distribution Gain",
                "uplift_pct": 0.05,
                "comment": "legacy",
                "created_by": "Key Account Manager",
                "created_at": pd.Timestamp("2025-01-01"),
            }
        ]
    )
    db.insert_df("overrides", legacy)
    context.bump_overrides()
    try:
        rows = {o["override_id"]: o for o in api_client.get("/api/overrides").json()}
        assert rows["OVR-LEGACY01"]["event_type"] == "Ganho de distribuição"
        assert rows["OVR-LEGACY01"]["created_by"] == "Key Account (KAM)"
        detail = api_client.get("/api/forecast/series-detail", params={"series_id": sid}).json()
        legacy_row = next(o for o in detail["overrides"] if o["override_id"] == "OVR-LEGACY01")
        assert (legacy_row["event_type"], legacy_row["created_by"]) == ("Ganho de distribuição", "Key Account (KAM)")
        assert api_client.get("/api/export/excel").status_code == 200
        upd = api_client.put(
            "/api/overrides/OVR-LEGACY01",
            json={
                "customer": cust,
                "sku": sku,
                "date": str(ctx.future_dates[2].date()),
                "event_type": "Promotion",
                "uplift_pct": 0.05,
                "created_by": "Sales Director",
            },
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["event_type"] == "Promoção" and upd.json()["created_by"] == "Diretor de Vendas"
    finally:
        api_client.delete("/api/overrides/OVR-LEGACY01")


def test_presets_migrate_from_english(ctx):
    """Databases created by the English version get the Portuguese preset names and descriptions."""
    from app import db
    from app.scenarios import store

    store.ensure_presets(ctx)
    db.execute(
        "UPDATE scenarios SET name = 'Conservative', description = ? WHERE scenario_id = 'SCN-CONSERVATIVE'",
        ["Price pass-through, slight distribution loss, lower marketing and a softer market."],
    )
    db.execute("UPDATE scenarios SET name = 'Meu agressivo' WHERE scenario_id = 'SCN-AGGRESSIVE'")
    store.refresh_presets(ctx)
    by_id = {s["scenario_id"]: s for s in store.list_scenarios()}
    assert by_id["SCN-CONSERVATIVE"]["name"] == "Conservador"
    assert by_id["SCN-CONSERVATIVE"]["description"].startswith("Repasse de preço")
    assert by_id["SCN-AGGRESSIVE"]["name"] == "Meu agressivo"  # renamed by the user: kept
    assert by_id["SCN-BASE"]["name"] == "Base"
    db.execute("UPDATE scenarios SET name = 'Agressivo' WHERE scenario_id = 'SCN-AGGRESSIVE'")


def test_hierarchy_levels_sum_to_total(api_client):
    region = api_client.get("/api/forecast/hierarchy", params={"level": "region"}).json()["rows"]
    company = api_client.get("/api/forecast/hierarchy", params={"level": "company"}).json()["rows"]
    assert sum(r["forecast_12m"] for r in region) == pytest.approx(company[0]["forecast_12m"])
    assert company[0]["member"] == "Empresa (total)"
