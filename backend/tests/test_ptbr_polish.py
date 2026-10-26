"""pt-BR polish: upload template round trip, plan-sheet aliases, Portuguese errors and texts, scoped alerts."""

from __future__ import annotations

import io
from types import SimpleNamespace

import pandas as pd
import pytest
from openpyxl import Workbook

from app.ingestion.readers import UnsupportedFileError, read_table
from app.ingestion.schema import (
    CANONICAL,
    HEADERS_PT,
    PLAN_HEADERS_PT,
    is_plan_sheet,
    map_columns,
    map_plan_columns,
)
from app.ingestion.template import EXAMPLE, PLAN_EXAMPLE, build_template
from app.validation.health import validate_and_normalize

ENGLISH = ("Required", "Optional", "Column", "Description", "Instructions", "Customer A", "Cliente A")


def _sheet_text(content: bytes, sheet: str) -> str:
    df = pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=None)
    return " ".join(str(v) for v in df.to_numpy().ravel() if pd.notna(v))


def _workbook(sheets: dict[str, list[list]]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- template
def test_template_is_portuguese_and_round_trips():
    from app.api.data import _read_plan

    content = build_template()
    xl = pd.ExcelFile(io.BytesIO(content))
    assert xl.sheet_names == ["Dados", "Instruções", "Plano (opcional)"]

    raw = read_table(content, "modelo.xlsx")
    assert list(raw.columns) == [HEADERS_PT[c] for c in CANONICAL]
    assert set(map_columns(list(raw.columns)).values()) == set(CANONICAL)
    assert {"Sudeste", "Varejo Moderno", "Bebidas"} <= set(raw.to_numpy().ravel().tolist())

    report, norm = validate_and_normalize(raw)
    assert report.can_forecast and norm is not None
    assert report.summary["n_series"] == len({(r["customer"], r["sku"]) for r in EXAMPLE})
    assert not [i for i in report.issues if i.severity == "critical"]

    plan = _read_plan(content, "modelo.xlsx", norm)
    assert plan is not None and len(plan) == 1
    row = plan.iloc[0]
    assert (row["customer"], row["sku"]) == (PLAN_EXAMPLE[1], PLAN_EXAMPLE[2])
    assert (row["budget_units"], row["target_units"]) == (PLAN_EXAMPLE[3], PLAN_EXAMPLE[4])
    assert (row["budget_revenue"], row["target_revenue"]) == (PLAN_EXAMPLE[5], PLAN_EXAMPLE[6])
    assert row["date"] == pd.Timestamp(PLAN_EXAMPLE[0])


def test_template_instructions_are_portuguese():
    content = build_template()
    text = _sheet_text(content, "Instruções")
    for word in ("Coluna", "Obrigatória", "Descrição", "Sim", "Opcional", "Plano (opcional)", "Wallison Sampaio"):
        assert word in text
    for header in [*HEADERS_PT.values(), *PLAN_HEADERS_PT.values()]:
        assert header in text
    for english in ENGLISH:
        assert english not in text
    data_text = _sheet_text(content, "Dados")
    assert "Atlas Hipermercados" in data_text and "Cliente A" not in data_text
    plan = pd.read_excel(io.BytesIO(content), sheet_name="Plano (opcional)")
    assert list(plan.columns) == list(PLAN_HEADERS_PT.values())


# --------------------------------------------------------------------------- aliases
@pytest.mark.parametrize(
    ("header", "canonical"),
    [
        ("Local do Cliente", "customer_location"),
        ("LOCAL DO CLIENTE", "customer_location"),
        ("Potencial do Cliente", "customer_potential"),
        ("potencial do cliente", "customer_potential"),
        ("Investimento em Marketing", "marketing_investment"),
        ("INVESTIMENTO EM MARKETING", "marketing_investment"),
        ("Região", "region"),
        ("REGIAO", "region"),
        ("Preço", "price"),
        ("Promoção", "promotion"),
        ("Distribuição Numérica", "distribution"),
        ("Unidades Vendidas", "units"),
        ("Ação de Merchandising", "merchandising_event"),
    ],
)
def test_portuguese_data_headers_are_recognised(header, canonical):
    assert map_columns([header]) == {header: canonical}


@pytest.mark.parametrize(
    ("header", "canonical"),
    [
        ("Orçamento (unidades)", "budget_units"),
        ("OrçamentoUnidades", "budget_units"),
        ("ORCAMENTO UNIDADES", "budget_units"),
        ("BudgetUnits", "budget_units"),
        ("Meta (unidades)", "target_units"),
        ("MetaUnidades", "target_units"),
        ("meta unidades", "target_units"),
        ("TargetUnits", "target_units"),
        ("Orçamento (receita)", "budget_revenue"),
        ("Orçamento (R$)", "budget_revenue"),
        ("Meta (receita)", "target_revenue"),
        ("Meta R$", "target_revenue"),
        ("Data", "date"),
        ("Mês", "date"),
        ("Cliente", "customer"),
        ("SKU", "sku"),
    ],
)
def test_plan_headers_are_recognised(header, canonical):
    assert map_plan_columns([header]) == {canonical: header}


def test_aliases_are_unambiguous():
    from app.ingestion.schema import _ALIASES, PLAN_ALIASES, normalize_key

    for aliases in (_ALIASES, PLAN_ALIASES):
        keys = [normalize_key(a) for values in aliases.values() for a in values]
        assert len(keys) == len(set(keys))


# --------------------------------------------------------------------------- plan sheet names
SALES_ROWS = [["Data", "Região", "Canal", "Cliente", "SKU", "Unidades"]] + [
    [pd.Timestamp(2024, m, 1).to_pydatetime(), "Sul", "Farma", "CuraMais Farmácias", "SKU-10101", 100 + m]
    for m in range(1, 8)
]


@pytest.mark.parametrize(
    "sheet",
    ["Plano", "Plano (opcional)", "PLANO (OPCIONAL)", "plano", "Orçamento", "ORCAMENTO", "Plan", "Plan (optional)"],
)
@pytest.mark.parametrize(
    "headers",
    [
        ["Data", "Cliente", "SKU", "Orçamento (unidades)", "Meta (unidades)"],
        ["Mês", "Cliente", "SKU", "OrçamentoUnidades", "MetaUnidades"],
        ["Date", "Customer", "SKU", "BudgetUnits", "TargetUnits"],
    ],
)
def test_plan_sheet_names_and_headers_are_case_and_accent_insensitive(sheet, headers):
    from app.api.data import _read_plan

    plan_rows = [headers, [pd.Timestamp(2024, 9, 1).to_pydatetime(), "CuraMais Farmácias", "SKU-10101", 120, 130]]
    content = _workbook({"Dados": SALES_ROWS, sheet: plan_rows})
    _, norm = validate_and_normalize(read_table(content, "base.xlsx"))
    assert norm is not None
    plan = _read_plan(content, "base.xlsx", norm)
    assert plan is not None and len(plan) == 1
    assert (plan.iloc[0]["budget_units"], plan.iloc[0]["target_units"]) == (120, 130)
    assert pd.isna(plan.iloc[0]["budget_revenue"])


def test_generic_excel_sheet_names_are_not_plan_sheets():
    assert not is_plan_sheet("Planilha1") and not is_plan_sheet("Plan1") and not is_plan_sheet("Planilha")
    assert not is_plan_sheet("Planilha de Vendas") and not is_plan_sheet("Metadados")
    assert is_plan_sheet("Plano") and is_plan_sheet("Plan") and is_plan_sheet("Budget 2026")
    assert is_plan_sheet("Meta 2026") and is_plan_sheet("Orçamento 2026")


def test_plan_sheet_values_are_cleaned_and_unknown_pairs_dropped():
    from app.api.data import _read_plan

    headers = ["Data", "Cliente", "SKU", "Orçamento (unidades)", "Meta (unidades)"]
    rows = [
        headers,
        [pd.Timestamp(2024, 9, 1).to_pydatetime(), " CuraMais Farmácias ", "SKU-10101 ", "120", 130],
        [pd.Timestamp(2024, 10, 1).to_pydatetime(), "CuraMais Farmácias", "SKU-10101", None, None],
        ["sem data", "CuraMais Farmácias", "SKU-10101", 120, 130],
    ]
    content = _workbook({"Dados": SALES_ROWS, "Plano": rows})
    _, norm = validate_and_normalize(read_table(content, "base.xlsx"))
    plan = _read_plan(content, "base.xlsx", norm)
    assert plan is not None and len(plan) == 1
    assert (plan.iloc[0]["customer"], plan.iloc[0]["sku"]) == ("CuraMais Farmácias", "SKU-10101")
    assert (plan.iloc[0]["budget_units"], plan.iloc[0]["target_units"]) == (120, 130)

    unknown = [headers, [pd.Timestamp(2024, 9, 1).to_pydatetime(), "Outro Cliente", "SKU-10101", 120, 130]]
    content = _workbook({"Dados": SALES_ROWS, "Plano": unknown})
    assert _read_plan(content, "base.xlsx", norm) is None


def test_blank_plan_revenue_is_units_times_recent_price():
    from app.api.data import _read_plan

    # Months 1-7 at R$ 2,00, except the last 6 months average exactly R$ 2,50 (months 2-7 at R$ 2,50).
    sales = [[*SALES_ROWS[0], "Receita"]] + [[*r, r[-1] * (2.0 if r[0].month == 1 else 2.5)] for r in SALES_ROWS[1:]]
    headers = ["Data", "Cliente", "SKU", "Orçamento (unidades)", "Meta (unidades)", "Orçamento (receita)"]
    rows = [
        headers,
        [pd.Timestamp(2024, 9, 1).to_pydatetime(), "CuraMais Farmácias", "SKU-10101", 100, 110, None],
        [pd.Timestamp(2024, 10, 1).to_pydatetime(), "CuraMais Farmácias", "SKU-10101", 100, 110, 999.0],
    ]
    content = _workbook({"Dados": sales, "Plano": rows})
    _, norm = validate_and_normalize(read_table(content, "base.xlsx"))
    plan = _read_plan(content, "base.xlsx", norm)
    assert plan["budget_revenue"].tolist() == pytest.approx([250.0, 999.0])
    assert plan["target_revenue"].tolist() == pytest.approx([275.0, 275.0])


def test_reader_prefers_the_data_sheet():
    instructions = [["Leia antes de preencher"]]
    plan = [["Data", "Cliente", "SKU", "Orçamento (unidades)", "Meta (unidades)"]]
    content = _workbook({"Instruções": instructions, "Plano": plan, "Vendas": SALES_ROWS})
    assert list(read_table(content, "base.xlsx").columns) == SALES_ROWS[0]
    content = _workbook({"Instruções": instructions, "Planilha1": SALES_ROWS})
    assert list(read_table(content, "base.xlsx").columns) == SALES_ROWS[0]
    content = _workbook({"Planilha de Vendas": SALES_ROWS, "Resumo": [["Total"]]})
    assert list(read_table(content, "base.xlsx").columns) == SALES_ROWS[0]


def test_unsupported_file_message_is_portuguese():
    with pytest.raises(UnsupportedFileError, match=r"^Tipo de arquivo não suportado \(\.txt\)\. Use um destes"):
        read_table(b"abc", "dados.txt")


def test_xls_without_reader_package_explains_how_to_fix(monkeypatch, api_client):
    from app.ingestion import readers

    def no_xlrd(*_args, **_kwargs):
        raise ImportError("Missing optional dependency 'xlrd'.")

    monkeypatch.setattr(readers.pd, "ExcelFile", no_xlrd)
    with pytest.raises(UnsupportedFileError, match=r"\.xls \(Excel 97-2003\).*Salve a planilha como \.xlsx"):
        read_table(b"\xd0\xcf\x11\xe0", "dados.xls")
    r = api_client.post(
        "/api/data/upload", files={"file": ("dados.xls", b"\xd0\xcf\x11\xe0", "application/vnd.ms-excel")}
    )
    assert r.status_code == 400 and r.json()["detail"] == readers.XLS_UNAVAILABLE


# --------------------------------------------------------------------------- API errors
def test_upload_errors_are_portuguese_without_raw_exception_text(api_client):
    from app.api.data import READ_ERROR

    r = api_client.post("/api/data/upload", files={"file": ("dados.txt", b"abc", "text/plain")})
    assert r.status_code == 400 and r.json()["detail"].startswith("Tipo de arquivo não suportado (.txt).")
    r = api_client.post("/api/data/upload", files={"file": ("dados.xlsx", b"corrompido", "application/zip")})
    assert r.status_code == 400 and r.json()["detail"] == READ_ERROR
    r = api_client.post("/api/data/upload", files={"file": ("dados.csv", b"", "text/csv")})
    assert r.status_code == 400 and r.json()["detail"] == READ_ERROR


def test_forecast_errors_are_portuguese(api_client):
    r = api_client.get("/api/forecast/runs/RUN-NAO-EXISTE")
    assert r.status_code == 404 and r.json()["detail"] == "Execução não encontrada"
    r = api_client.post("/api/forecast/runs/RUN-NAO-EXISTE/activate")
    assert r.status_code == 404 and r.json()["detail"] == "Execução concluída não encontrada"
    r = api_client.get("/api/forecast/series-detail", params={"series_id": "Cliente X|SKU-0"})
    assert r.status_code == 404 and r.json()["detail"] == "Série 'Cliente X · SKU-0' não encontrada"
    r = api_client.post("/api/forecast/run", json={"horizon": 7})
    assert r.status_code == 400 and "3, 6, 12, 18 ou 24 meses" in r.json()["detail"]
    assert api_client.delete("/api/overrides/OVR-NAO-EXISTE").json()["detail"] == "Ajuste comercial não encontrado"


def test_override_default_planner_is_portuguese():
    from app.api.forecast import OverrideRequest

    req = OverrideRequest(date="2030-01-01", event_type="Promoção", uplift_pct=0.1)
    assert req.created_by == "Planejador de Demanda"


# --------------------------------------------------------------------------- texts
def test_model_descriptions_are_portuguese():
    from app.forecasting.models import model_catalog
    from app.services.ptbr import MODEL_DESCRIPTION

    catalog = model_catalog()
    assert catalog
    for m in catalog:
        assert m["description"] == MODEL_DESCRIPTION[m["name"]]


def test_alert_texts_are_portuguese(api_client):
    alerts = api_client.get("/api/alerts").json()["alerts"]
    fields = ("title", "issue", "magnitude", "explanation", "recommendation")
    text = " ".join(str(a.get(f) or "") for a in alerts for f in fields)
    for english in ("Tracking signal", "fold", "Target", "Budget", "Revenue", "Forecast error"):
        assert english not in text
    for a in alerts:
        if a["type"] == "structural_change":
            assert a["magnitude"].startswith("Sinal de rastreamento ")


# --------------------------------------------------------------------------- scoped alerts
def _alert(kind: str, entity: dict) -> dict:
    return {"type": kind, "severity": "high", "entity": entity}


def test_filter_alerts_keeps_series_and_customers_in_scope():
    from app.alerts.engine import filter_alerts

    series = pd.DataFrame(
        {
            "series_id": ["A|1", "A|2", "B|1"],
            "customer": ["A", "A", "B"],
            "region": ["Sul", "Sul", "Norte"],
        }
    )
    ctx = SimpleNamespace(series=series)
    alerts = [
        _alert("high_error", {"series_id": "A|1", "customer": "A", "sku": "1"}),
        _alert("high_error", {"series_id": "B|1", "customer": "B", "sku": "1"}),
        _alert("target_above_p90", {"customer": "A", "region": "Sul"}),
        _alert("opportunity", {"customer": "B", "region": "Norte"}),
    ]
    assert filter_alerts(ctx, alerts, pd.Index(series["series_id"])) == alerts
    scoped = filter_alerts(ctx, alerts, pd.Index(["A|2"]))
    assert scoped == [alerts[2]]
    scoped = filter_alerts(ctx, alerts, pd.Index(["A|1", "A|2"]))
    assert scoped == [alerts[0], alerts[2]]
    assert filter_alerts(ctx, alerts, pd.Index([])) == []


def test_overview_alerts_follow_the_filters(api_client):
    full = api_client.get("/api/overview").json()
    customers = api_client.get("/api/data/dimensions").json()["customer"]
    assert len(customers) == 2
    totals = []
    for cust in customers:
        part = api_client.get("/api/overview", params={"customer": cust}).json()
        assert all(a["entity"]["customer"] == cust for a in part["alerts"])
        assert part["kpis"]["risk_skus"] <= full["kpis"]["risk_skus"]
        totals.append(part["alert_counts"])
    for sev, n in full["alert_counts"].items():
        assert sum(t[sev] for t in totals) == n
