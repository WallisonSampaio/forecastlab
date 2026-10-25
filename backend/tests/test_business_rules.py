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
    assert r["message"] == "Override reduced forecast accuracy."
    good = evaluate_override(statistical=100, override_pct=0.20, actual=118)
    assert good["outcome"] == "Improved" and good["fva_units"] == pytest.approx(16)


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
            "event_type": "Promotion",
            "uplift_pct": 0.15,
            "comment": "test",
        },
    )
    assert r.status_code == 200, r.text
    from app.services.context import get_context

    f = get_context().forecast
    cons = f.loc[(f["series_id"] == sid) & (f["date"] == month), "consensus"].item()
    assert cons == pytest.approx(base * 1.15)
    api_client.delete(f"/api/overrides/{r.json()['override_id']}")
    f = get_context().forecast
    assert f.loc[(f["series_id"] == sid) & (f["date"] == month), "consensus"].item() == pytest.approx(base)


def test_hierarchy_levels_sum_to_total(api_client):
    region = api_client.get("/api/forecast/hierarchy", params={"level": "region"}).json()["rows"]
    company = api_client.get("/api/forecast/hierarchy", params={"level": "company"}).json()["rows"]
    assert sum(r["forecast_12m"] for r in region) == pytest.approx(company[0]["forecast_12m"])
