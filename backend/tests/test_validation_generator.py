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
            "Region": "South",
            "Channel": "Modern Trade",
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
    assert report.to_dict()["blocking_message"].startswith("Forecast execution blocked")


def test_negative_units_and_invalid_dates_are_critical():
    df = _base_rows().astype({"Date": "object"})
    df.loc[3, "Units"] = -5
    df.loc[5, "Date"] = "not a date"
    report, norm = validate_and_normalize(df)
    codes = {i.code: i.severity for i in report.issues}
    assert codes["negative_units"] == "critical" and codes["invalid_dates"] == "critical"
    assert norm is None


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
