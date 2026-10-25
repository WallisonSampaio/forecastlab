"""End-to-end API smoke tests on a small synthetic dataset (forecast run included)."""

import io

import pandas as pd
import pytest


def test_health_and_meta(api_client):
    assert api_client.get("/api/health").json()["status"] == "ok"
    meta = api_client.get("/api/meta").json()
    assert meta["author"]["name"] == "Wallison Sampaio"
    assert len(meta["models"]) >= 8


def test_run_registry_and_model_registry(api_client):
    runs = api_client.get("/api/forecast/runs").json()
    assert runs[0]["status"] == "completed"
    assert {"run_id", "created_at", "dataset_version", "horizon", "model_version", "scenario", "status"} <= set(runs[0])
    reg = api_client.get("/api/models/registry").json()
    assert {
        "series_id",
        "model",
        "model_version",
        "training_date",
        "wmape",
        "bias",
        "parameters",
        "champion_flag",
    } <= set(reg[0])


@pytest.mark.parametrize(
    "path",
    [
        "/api/overview",
        "/api/data/dimensions",
        "/api/data/eda",
        "/api/data/profiles",
        "/api/forecast/series",
        "/api/forecast/aggregate?measure=revenue",
        "/api/forecast/hierarchy?level=customer",
        "/api/models/leaderboard",
        "/api/models/distribution",
        "/api/models/heatmap?metric=bias",
        "/api/models/performance",
        "/api/scenarios",
        "/api/scenarios/compare",
        "/api/sop/cockpit",
        "/api/sop/feasibility",
        "/api/fva",
        "/api/alerts",
        "/api/semantic/catalog",
    ],
)
def test_read_endpoints(api_client, path):
    r = api_client.get(path)
    assert r.status_code == 200, r.text


def test_series_detail_has_champion_challenger_and_interval(api_client):
    sid = api_client.get("/api/forecast/series").json()[0]["series_id"]
    d = api_client.get("/api/forecast/series-detail", params={"series_id": sid}).json()
    assert d["selection"]["champion"]
    nm = d["next_month"]
    assert nm["p10"] <= nm["base"] <= nm["p90"]
    assert len([r for r in d["timeline"] if r.get("base") is not None]) == 12


def test_scenario_crud_and_compare(api_client):
    s = api_client.post("/api/scenarios", json={"name": "Test", "params": {"price_change_pct": -0.05}}).json()
    dup = api_client.post(f"/api/scenarios/{s['scenario_id']}/duplicate").json()
    upd = api_client.put(f"/api/scenarios/{dup['scenario_id']}", json={"name": "Edited", "params": {}}).json()
    assert upd["name"] == "Edited"
    rows = api_client.get("/api/scenarios/compare").json()["rows"]
    assert {r["name"] for r in rows} >= {"Base", "Conservative", "Aggressive", "Test", "Edited"}
    assert api_client.delete("/api/scenarios/SCN-BASE").status_code == 403
    assert api_client.delete(f"/api/scenarios/{s['scenario_id']}").status_code == 200


def test_allocation_endpoint(api_client):
    r = api_client.post("/api/sop/allocation", json={"dimension": "region", "method": "forecast"}).json()
    assert r["rows"] and r["total_target"] > 0


def test_upload_blocked_file_does_not_create_dataset(api_client):
    before = len(api_client.get("/api/data/datasets").json())
    bad = pd.DataFrame({"Date": ["2024-01-01"], "Customer": ["A"], "SKU": ["X"], "Units": [-1]})
    files = {"file": ("bad.csv", bad.to_csv(index=False).encode(), "text/csv")}
    r = api_client.post("/api/data/upload", files=files).json()
    assert r["accepted"] is False
    assert r["validation"]["blocking_message"].startswith("Forecast execution blocked")
    assert len(api_client.get("/api/data/datasets").json()) == before


def test_exports_and_template(api_client):
    x = api_client.get("/api/export/excel")
    assert x.status_code == 200 and x.content[:2] == b"PK"
    sheets = pd.ExcelFile(io.BytesIO(x.content)).sheet_names
    assert {"Cover", "Executive Summary", "Forecast Detail", "Model Leaderboard", "FVA"} <= set(sheets)
    detail = pd.read_excel(io.BytesIO(x.content), sheet_name="Forecast Detail")
    for col in (
        "Actual Units",
        "Statistical Forecast",
        "Consensus Forecast",
        "Budget Units",
        "Target Units",
        "P10",
        "P50",
        "P90",
        "WMAPE",
        "Bias",
        "Champion Model",
    ):
        assert col in detail.columns
    html = api_client.get("/api/export/executive-html").text
    assert "Wallison Sampaio" in html and "<svg" in html
    t = api_client.get("/api/data/template")
    assert pd.ExcelFile(io.BytesIO(t.content)).sheet_names[0] == "Data"
