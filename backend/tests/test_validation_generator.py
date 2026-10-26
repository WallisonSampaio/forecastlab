import pandas as pd

from app.ingestion.schema import map_columns
from app.validation.health import validate_and_normalize
from synthetic_data_generator import generate_dataset

PRD_FIELDS = [
    "Date",
    "Region",
    "Channel",
    "Customer",
    "CustomerLocation",
    "CustomerPotential",
    "SKU",
    "Product",
    "Category",
    "Brand",
    "Units",
    "Revenue",
    "Price",
    "Promotion",
    "Distribution",
    "StockOut",
    "Holiday",
    "MarketingInvestment",
    "MerchandisingEvent",
]


def _base_rows() -> pd.DataFrame:
    dates = pd.date_range("2023-01-01", periods=24, freq="MS")
    return pd.DataFrame(
        {
            "Date": dates,
            "Region": "Sul",
            "Channel": "Varejo Moderno",
            "Customer": "A",
            "SKU": "X",
            "Units": range(100, 124),
        }
    )


def test_generator_is_reproducible_and_seed_sensitive():
    a, b, c = generate_dataset(11), generate_dataset(11), generate_dataset(12)
    pd.testing.assert_frame_equal(a.sales, b.sales)
    assert not a.sales["Units"].equals(c.sales["Units"])


def test_generator_schema_and_history(demo):
    assert list(demo.sales.columns) == PRD_FIELDS
    assert demo.sales["Date"].nunique() == 60
    assert (demo.sales["Units"] >= 0).all()
    assert set(demo.metadata["sku_patterns"].values()) >= {
        "Stable",
        "Trending",
        "Declining",
        "Seasonal",
        "Intermittent",
        "Promo Driven",
        "Distribution Driven",
        "Structural Change",
        "Volatile",
    }
    assert len(demo.plan) > 0 and len(demo.historical_overrides) > 0


def test_valid_file_passes_with_quality_score():
    report, norm = validate_and_normalize(_base_rows())
    assert report.can_forecast and norm is not None
    assert 0 < report.quality["overall"] <= 100
    assert report.summary["n_series"] == 1


def test_missing_required_columns_block_execution():
    report, norm = validate_and_normalize(_base_rows().drop(columns=["Channel"]))
    assert not report.can_forecast and norm is None
    d = report.to_dict()
    assert d["blocking_message"] == "Execução do forecast bloqueada. Corrija os erros críticos listados abaixo."
    missing = next(i for i in d["issues"] if i["code"] == "missing_columns")
    assert missing["message"] == "Coluna(s) obrigatória(s) ausente(s): Canal"


def test_negative_units_and_invalid_dates_are_critical():
    df = _base_rows().astype({"Date": "object"})
    df.loc[3, "Units"] = -5
    df.loc[5, "Date"] = "not a date"
    report, norm = validate_and_normalize(df)
    codes = {i.code: i.severity for i in report.issues}
    assert codes["negative_units"] == "critical" and codes["invalid_dates"] == "critical"
    assert norm is None
    messages = {i.code: i.message for i in report.issues}
    assert messages["invalid_dates"] == "1 linha(s) com data inválida"
    assert messages["negative_units"].startswith("1 linha(s) com unidades negativas")


def test_score_labels_and_number_format_are_portuguese():
    from app.validation.health import issue_message, score_label

    assert [score_label(s) for s in (95, 80, 65, 40)] == ["Excelente", "Bom", "Regular", "Ruim"]
    assert issue_message("duplicated_rows", 1234567) == "1.234.567 linha(s) totalmente duplicada(s) (removidas)"
    assert issue_message("missing_customer", 3) == "3 linha(s) sem cliente"
    assert issue_message("non_numeric_price", 2) == "2 valor(es) não numérico(s) em Preço"


def test_reports_stored_in_english_are_rendered_in_portuguese():
    from app.validation.health import localize_report

    legacy = {
        "status": "blocked",
        "summary": {"history": {"max_months": 4}},
        "issues": [
            {
                "severity": "critical",
                "code": "missing_columns",
                "message": "Missing required column(s): channel",
                "count": 1,
                "examples": ["channel"],
            },
            {"severity": "critical", "code": "insufficient_history", "message": "At least 6 months...", "count": 0},
            {"severity": "warning", "code": "outliers", "message": "12 unexplained outliers", "count": 12},
        ],
        "blocking_message": "Forecast execution blocked. Fix the critical errors listed below.",
    }
    d = localize_report(legacy)
    assert [i["message"] for i in d["issues"]] == [
        "Coluna(s) obrigatória(s) ausente(s): Canal",
        "São necessários pelo menos 6 meses de histórico (encontrados: 4).",
        d["issues"][2]["message"],
    ]
    assert d["issues"][2]["message"].startswith("12 outlier(s) sem explicação")
    assert d["blocking_message"].startswith("Execução do forecast bloqueada")


def test_profiling_reasons_are_portuguese():
    import numpy as np

    from app.forecasting.profiling import classify

    p = {"n_obs": 40, "adi": 2.1, "zero_pct": 0.52}
    stype, reason = classify(p, np.ones(40))
    assert stype == "Intermittent"
    assert reason == "ADI 2,10 ≥ 1,32 (52% de meses sem demanda)"
    assert classify({"n_obs": 14}, np.ones(14)) == ("Short History", "Apenas 14 meses de histórico (< 24)")
    assert classify({"n_obs": 30}, np.r_[np.ones(24), np.zeros(6)]) == (
        "Inactive",
        "Sem demanda nos últimos 6 meses (possível deslistagem)",
    )


def test_legacy_english_profiling_reasons_are_translated():
    from app.forecasting.profiling import localize_reason

    cases = {
        "ADI 2.07 >= 1.32 (52% zero months)": "ADI 2,07 ≥ 1,32 (52% de meses sem demanda)",
        "Seasonal strength 0.64 >= 0.55": "Força sazonal 0,64 ≥ 0,55",
        "Level shift of -32% detected at month 34": "Mudança de patamar de -32% detectada no mês 34",
        "Trend strength 0.71, -11% per year": "Tendência forte 0,71, -11% ao ano",
        "Promotion lift +74% (corr 0.74)": "Uplift de promoção de +74% (corr 0,74)",
        "Demand tracks numeric distribution (corr 0.93, range 48 pts)": (
            "Demanda acompanha a distribuição numérica (corr 0,93, amplitude 48 pts)"
        ),
        "Only 17 months of history (< 24)": "Apenas 17 meses de histórico (< 24)",
        "Residual CV 0.36 >= 0.22": "CV residual 0,36 ≥ 0,22",
        "Low volatility (residual CV 0.10), no dominant pattern": (
            "Baixa volatilidade (CV residual 0,10), sem padrão dominante"
        ),
        "No demand in the last 6 months (possible delisting)": "Sem demanda nos últimos 6 meses (possível deslistagem)",
    }
    for legacy, expected in cases.items():
        assert localize_reason(legacy) == expected
    current = "Força sazonal 0,71 ≥ 0,55"
    assert localize_reason(current) == current and localize_reason(None) is None


def test_daily_rows_are_aggregated_to_monthly():
    dates = ["2024-01-05", "2024-01-20"] + [f"2024-{m:02d}-03" for m in range(2, 9)]
    df = pd.DataFrame(
        {
            "Data": dates,
            "Regiao": "S",
            "Canal": "MT",
            "Cliente": "A",
            "SKU": "X",
            "Quantidade": [10, 15, 7, 8, 9, 10, 11, 12, 13],
        }
    )
    report, norm = validate_and_normalize(df)
    assert norm is not None
    assert norm["units"].tolist() == [25, 7, 8, 9, 10, 11, 12, 13]
    assert any(i.code == "aggregated_to_monthly" for i in report.issues)


def test_column_aliases_pt_en():
    m = map_columns(["Data", "Região", "Canal", "Cliente", "Código", "Quantidade", "Preço", "Promoção"])
    assert set(m.values()) == {"date", "region", "channel", "customer", "sku", "units", "price", "promotion"}
