"""End-to-end API smoke tests on a small synthetic dataset (forecast run included)."""

import io

import pandas as pd
import pytest


def test_health_and_meta(api_client):
    assert api_client.get("/api/health").json()["status"] == "ok"
    r = api_client.get("/api/meta")
    meta = r.json()
    assert meta["author"]["name"] == "Wallison Sampaio"
    assert meta["author"]["title"].startswith("Especialista em Inteligência Comercial")
    assert len(meta["models"]) >= 8
    naive = next(m for m in meta["models"] if m["name"] == "Naive")
    assert naive["description"] == "Repete o último valor observado."
    # no filesystem paths exposed
    assert "db_path" not in meta
    assert ".duckdb" not in r.text and ":\\\\" not in r.text


def test_error_details_are_portuguese(api_client):
    r = api_client.post("/api/forecast/run", json={"horizon": 7})
    assert r.status_code == 400 and r.json()["detail"].startswith("Horizonte inválido")
    r = api_client.get("/api/forecast/series-detail", params={"series_id": "X|Y"})
    assert r.status_code == 404 and "não encontrada" in r.json()["detail"]
    r = api_client.post("/api/sop/allocation", json={"dimension": "planeta"})
    assert r.status_code == 400 and r.json()["detail"].startswith("Dimensão inválida")
    r = api_client.post("/api/overrides", json={"date": "2030-01-01"})
    assert r.status_code == 422 and r.json()["detail"].startswith("Requisição inválida")
    files = {"file": ("dados.txt", b"abc", "text/plain")}
    r = api_client.post("/api/data/upload", files=files)
    assert r.status_code == 400 and r.json()["detail"].startswith("Tipo de arquivo não suportado")
    r = api_client.post("/api/data/upload", files={"file": ("dados.xlsx", b"corrompido", "application/octet-stream")})
    assert r.status_code == 400 and r.json()["detail"].startswith("Não foi possível ler o arquivo.")
    r = api_client.get("/api/forecast/hierarchy", params={"level": "planeta"})
    assert r.status_code == 400 and "region (Região)" in r.json()["detail"]
    r = api_client.get("/api/rota-inexistente")
    assert r.status_code == 404 and r.json()["detail"] == "Recurso não encontrado."
    r = api_client.delete("/api/health")
    assert r.status_code == 405 and r.json()["detail"] == "Método não permitido para este endpoint."


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
    s = api_client.post("/api/scenarios", json={"name": "Teste", "params": {"price_change_pct": -0.05}}).json()
    dup = api_client.post(f"/api/scenarios/{s['scenario_id']}/duplicate").json()
    assert dup["name"] == "Teste (cópia)"
    upd = api_client.put(f"/api/scenarios/{dup['scenario_id']}", json={"name": "Editado", "params": {}}).json()
    assert upd["name"] == "Editado"
    rows = api_client.get("/api/scenarios/compare").json()["rows"]
    assert {r["name"] for r in rows} >= {"Base", "Conservador", "Agressivo", "Teste", "Editado"}
    r = api_client.delete("/api/scenarios/SCN-BASE")
    assert r.status_code == 403 and r.json()["detail"] == "O cenário Base não pode ser excluído."
    assert api_client.delete("/api/scenarios/SCN-NAO-EXISTE").json()["detail"] == "Cenário não encontrado"
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
    assert r["validation"]["blocking_message"].startswith("Execução do forecast bloqueada")
    assert all(i["message"] for i in r["validation"]["issues"])
    assert len(api_client.get("/api/data/datasets").json()) == before


def test_exports_are_portuguese(api_client):
    x = api_client.get("/api/export/excel")
    assert x.status_code == 200 and x.content[:2] == b"PK"
    assert "forecastlab_plano_" in x.headers["content-disposition"]
    sheets = pd.ExcelFile(io.BytesIO(x.content)).sheet_names
    assert sheets == [
        "Capa",
        "Resumo Executivo",
        "Detalhe do Forecast",
        "Ranking de Modelos",
        "Performance das Séries",
        "Cenários",
        "Viabilidade da Meta",
        "FVA",
        "Alertas",
        "Ajustes Comerciais",
    ]
    detail = pd.read_excel(io.BytesIO(x.content), sheet_name="Detalhe do Forecast")
    for col in (
        "Mês",
        "Unidades reais",
        "Forecast estatístico",
        "Forecast de consenso",
        "Orçamento (unidades)",
        "Meta (unidades)",
        "P10",
        "P50",
        "P90",
        "WMAPE",
        "Viés",
        "Modelo campeão",
        "Confiança",
    ):
        assert col in detail.columns
    assert set(detail["Tipo"]) == {"Real", "Forecast"}
    assert set(detail["Confiança"].dropna()) <= {"Alta", "Média", "Baixa"}
    summary = pd.read_excel(io.BytesIO(x.content), sheet_name="Resumo Executivo")
    assert list(summary.columns) == ["Indicador", "Valor"]
    assert "Receita em risco (R$)" in set(summary["Indicador"])
    scen = pd.read_excel(io.BytesIO(x.content), sheet_name="Cenários")
    assert {"Base", "Conservador", "Agressivo"} <= set(scen["Cenário"])
    cover = pd.read_excel(io.BytesIO(x.content), sheet_name="Capa", header=None)
    cover_text = " ".join(str(v) for v in cover.to_numpy().ravel())
    assert "Desenvolvido por Wallison Sampaio" in cover_text and "Gerado em" in cover_text

    ex = api_client.get("/api/export/executive-excel")
    assert pd.ExcelFile(io.BytesIO(ex.content)).sheet_names[0] == "Capa"

    html = api_client.get("/api/export/executive-html").text
    assert "Wallison Sampaio" in html and "<svg" in html
    assert 'lang="pt-BR"' in html and "Relatório Executivo de S&amp;OP" in html
    assert "Desenvolvido por Wallison Sampaio · Especialista em Inteligência Comercial" in html
    for english in (
        "Executive S&amp;OP Report",
        "Target feasibility",
        "Alert center",
        "Revenue at risk",
        "Forecast Value Added",
    ):
        assert english not in html


def test_template_round_trips(api_client):
    from app.api.data import _read_plan
    from app.ingestion.schema import CANONICAL, map_columns

    t = api_client.get("/api/data/template")
    assert t.status_code == 200
    assert "forecastlab_modelo_de_planilha.xlsx" in t.headers["content-disposition"]
    xl = pd.ExcelFile(io.BytesIO(t.content))
    assert xl.sheet_names == ["Dados", "Instruções", "Plano (opcional)"]
    data = xl.parse("Dados")
    assert set(map_columns(list(data.columns)).values()) == set(CANONICAL)
    sales = pd.DataFrame({"customer": ["Atlas Hipermercados"], "sku": ["SKU-10101"]})
    plan = _read_plan(t.content, "modelo.xlsx", sales)
    assert plan is not None and len(plan) == 1
    row = plan.iloc[0]
    assert (row["budget_units"], row["target_units"], row["target_revenue"]) == (1300, 1400, 3486.0)
    assert row["date"] == pd.Timestamp("2025-01-01")
