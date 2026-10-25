"""Dataset lifecycle: versioning, storage, activation, demo bootstrap."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from app import db
from app.ingestion.schema import CANONICAL
from app.validation.health import ValidationReport, validate_and_normalize
from synthetic_data_generator import generate_dataset

PLAN_COLUMNS = ["date", "customer", "sku", "budget_units", "target_units", "budget_revenue", "target_revenue"]


def next_version(now: datetime | None = None) -> str:
    """dataset_YYYY_MM_vNN - NN counts uploads within the month."""
    now = now or datetime.now()
    prefix = f"dataset_{now:%Y_%m}_v"
    existing = db.query_df("SELECT dataset_version FROM datasets WHERE dataset_version LIKE ?", [prefix + "%"])
    nums = [int(v.rsplit("_v", 1)[1]) for v in existing["dataset_version"] if v.rsplit("_v", 1)[1].isdigit()]
    return f"{prefix}{(max(nums) + 1) if nums else 1:02d}"


def active_version() -> str | None:
    return db.get_state("active_dataset")


def list_datasets() -> pd.DataFrame:
    return db.query_df(
        "SELECT dataset_version, name, source, file_name, created_at, n_rows, n_series, n_skus, n_customers, "
        "start_date, end_date, quality_score, status, is_active, plan_source FROM datasets ORDER BY created_at DESC"
    )


def get_dataset(version: str) -> dict[str, Any] | None:
    df = db.query_df("SELECT * FROM datasets WHERE dataset_version = ?", [version])
    if df.empty:
        return None
    row = df.iloc[0].to_dict()
    row["validation"] = json.loads(row.pop("validation_json") or "{}")
    row["metadata"] = json.loads(row.pop("metadata_json") or "{}")
    return row


def activate(version: str) -> None:
    with db.locked() as con:
        con.execute("UPDATE datasets SET is_active = (dataset_version = ?)", [version])
    db.set_state("active_dataset", version)
    db.set_state("active_run", None)
    clear_caches()


def derive_plan(
    sales: pd.DataFrame, horizon: int = 12, budget_growth: float = 0.05, target_stretch: float = 0.05
) -> pd.DataFrame:
    """Budget = same month last year x (1 + growth); Target = Budget x (1 + stretch).

    Used when an uploaded dataset has no plan file. Covers the last 12 history
    months and the forecast horizon.
    """
    end = pd.Timestamp(sales["date"].max())
    months = pd.date_range(end - pd.DateOffset(months=11), periods=12 + horizon, freq="MS")
    pivot = sales.pivot_table(index=["customer", "sku"], columns="date", values="units", aggfunc="sum").fillna(0.0)
    rev = (
        sales.pivot_table(index=["customer", "sku"], columns="date", values="revenue", aggfunc="sum").fillna(0.0)
        if "revenue" in sales.columns
        else None
    )
    rows = []
    for key, hist in pivot.iterrows():
        price = 0.0
        if rev is not None:
            tail_u, tail_r = hist.tail(6).sum(), rev.loc[key].tail(6).sum()
            price = float(tail_r / tail_u) if tail_u else 0.0
        for d in months:
            ly = d - pd.DateOffset(years=1)
            base = float(hist.get(ly, np.nan))
            if np.isnan(base):
                base = float(hist.tail(3).mean())
            budget = base * (1 + budget_growth)
            target = budget * (1 + target_stretch)
            rows.append(
                {
                    "date": d,
                    "customer": key[0],
                    "sku": key[1],
                    "budget_units": round(budget),
                    "target_units": round(target),
                    "budget_revenue": round(budget * price * 1.03, 2),
                    "target_revenue": round(target * price * 1.03, 2),
                }
            )
    return pd.DataFrame(rows, columns=PLAN_COLUMNS)


def store_dataset(
    sales: pd.DataFrame,
    report: ValidationReport,
    *,
    name: str,
    source: str,
    file_name: str | None,
    plan: pd.DataFrame | None = None,
    plan_source: str | None = None,
    historical_overrides: pd.DataFrame | None = None,
    future_overrides: pd.DataFrame | None = None,
    metadata: dict[str, Any] | None = None,
    activate_now: bool = True,
) -> str:
    version = next_version()
    s = sales.copy()
    for c in CANONICAL:
        if c not in s.columns:
            s[c] = np.nan
    s["dataset_version"] = version
    if plan is None or plan.empty:
        plan = derive_plan(s)
        plan_source = plan_source or "Derived: same month last year x 1.05 (budget), x 1.05 stretch (target)"
    p = plan.copy()
    p["dataset_version"] = version
    summary = report.summary
    with db.locked() as con:
        con.execute(
            "INSERT INTO datasets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                version,
                name,
                source,
                file_name,
                datetime.now(),
                int(summary.get("rows", len(s))),
                int(summary.get("n_series", 0)),
                int(summary.get("n_skus", 0)),
                int(summary.get("n_customers", 0)),
                summary.get("start_date"),
                summary.get("end_date"),
                float(report.quality.get("overall", 0)),
                report.status,
                False,
                plan_source or "Uploaded plan",
                json.dumps(report.to_dict(), default=str),
                json.dumps(metadata or {}, default=str),
            ],
        )
    db.insert_df("sales", s)
    db.insert_df("plan", p)
    if historical_overrides is not None and not historical_overrides.empty:
        h = historical_overrides.copy()
        h["dataset_version"] = version
        db.insert_df("historical_overrides", h)
    if future_overrides is not None and not future_overrides.empty:
        f = future_overrides.copy()
        f["dataset_version"] = version
        f["override_id"] = [f"OVR-{uuid.uuid4().hex[:8].upper()}" for _ in range(len(f))]
        f["created_by"] = f.get("created_by", "Demo seed")
        f["created_at"] = datetime.now()
        db.insert_df("overrides", f)
    if activate_now:
        activate(version)
    return version


def _canonical_from_generator(df: pd.DataFrame) -> pd.DataFrame:
    ren = {
        "Date": "date",
        "Region": "region",
        "Channel": "channel",
        "Customer": "customer",
        "CustomerLocation": "customer_location",
        "CustomerPotential": "customer_potential",
        "SKU": "sku",
        "Product": "product",
        "Category": "category",
        "Brand": "brand",
        "Units": "units",
        "Revenue": "revenue",
        "Price": "price",
        "Promotion": "promotion",
        "Distribution": "distribution",
        "StockOut": "stockout",
        "Holiday": "holiday",
        "MarketingInvestment": "marketing_investment",
        "MerchandisingEvent": "merchandising_event",
    }
    return df.rename(columns=ren)


def load_demo_dataset(seed: int = 42, activate_now: bool = True) -> str:
    ds = generate_dataset(random_seed=seed)
    report, norm = validate_and_normalize(ds.sales)
    assert norm is not None, "synthetic dataset must always validate"
    plan = ds.plan.rename(
        columns={
            "Date": "date",
            "Customer": "customer",
            "SKU": "sku",
            "BudgetUnits": "budget_units",
            "TargetUnits": "target_units",
            "BudgetRevenue": "budget_revenue",
            "TargetRevenue": "target_revenue",
        }
    )
    hist = ds.historical_overrides.rename(
        columns={
            "Date": "date",
            "Customer": "customer",
            "SKU": "sku",
            "Planner": "planner",
            "EventType": "event_type",
            "AdjustmentPct": "adjustment_pct",
            "Comment": "comment",
        }
    )
    fut = ds.future_overrides.rename(
        columns={
            "Date": "date",
            "Customer": "customer",
            "SKU": "sku",
            "EventType": "event_type",
            "UpliftPct": "uplift_pct",
            "Comment": "comment",
        }
    )
    return store_dataset(
        _canonical_from_generator(ds.sales) if norm is None else norm,
        report,
        name=f"Synthetic demo dataset (seed {seed})",
        source="synthetic_generator",
        file_name=None,
        plan=plan,
        plan_source="Synthetic annual budget & sales targets",
        historical_overrides=hist,
        future_overrides=fut,
        metadata=ds.metadata,
        activate_now=activate_now,
    )


@lru_cache(maxsize=8)
def _sales_cached(version: str) -> pd.DataFrame:
    df = db.query_df("SELECT * FROM sales WHERE dataset_version = ? ORDER BY customer, sku, date", [version])
    df["date"] = pd.to_datetime(df["date"])
    return df


def get_sales(version: str | None = None) -> pd.DataFrame:
    version = version or active_version()
    if not version:
        return pd.DataFrame()
    return _sales_cached(version).copy()


@lru_cache(maxsize=8)
def _plan_cached(version: str) -> pd.DataFrame:
    df = db.query_df("SELECT * FROM plan WHERE dataset_version = ?", [version])
    df["date"] = pd.to_datetime(df["date"])
    return df


def get_plan(version: str | None = None) -> pd.DataFrame:
    version = version or active_version()
    return _plan_cached(version).copy() if version else pd.DataFrame(columns=PLAN_COLUMNS)


def get_historical_overrides(version: str | None = None) -> pd.DataFrame:
    version = version or active_version()
    df = db.query_df("SELECT * FROM historical_overrides WHERE dataset_version = ?", [version])
    df["date"] = pd.to_datetime(df["date"])
    return df


def clear_caches() -> None:
    _sales_cached.cache_clear()
    _plan_cached.cache_clear()
    from app.services import context

    context.invalidate()
