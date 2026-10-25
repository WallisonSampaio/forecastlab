"""DuckDB storage: one local analytical database file.

All access goes through a single connection guarded by a re-entrant lock;
datasets here are small (tens of thousands of rows), so simplicity wins.
The SQL is deliberately portable to PostgreSQL / Azure SQL (see docs).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from .config import settings

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS app_state (key VARCHAR PRIMARY KEY, value VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS datasets (
        dataset_version VARCHAR PRIMARY KEY, name VARCHAR, source VARCHAR, file_name VARCHAR,
        created_at TIMESTAMP, n_rows INTEGER, n_series INTEGER, n_skus INTEGER, n_customers INTEGER,
        start_date DATE, end_date DATE, quality_score DOUBLE, status VARCHAR, is_active BOOLEAN,
        plan_source VARCHAR, validation_json VARCHAR, metadata_json VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS sales (
        dataset_version VARCHAR, date DATE, region VARCHAR, channel VARCHAR, customer VARCHAR,
        customer_location VARCHAR, customer_potential DOUBLE, sku VARCHAR, product VARCHAR, category VARCHAR,
        brand VARCHAR, units DOUBLE, revenue DOUBLE, price DOUBLE, promotion DOUBLE, distribution DOUBLE,
        stockout DOUBLE, holiday DOUBLE, marketing_investment DOUBLE, merchandising_event DOUBLE)""",
    """CREATE TABLE IF NOT EXISTS plan (
        dataset_version VARCHAR, date DATE, customer VARCHAR, sku VARCHAR, budget_units DOUBLE,
        target_units DOUBLE, budget_revenue DOUBLE, target_revenue DOUBLE)""",
    """CREATE TABLE IF NOT EXISTS historical_overrides (
        dataset_version VARCHAR, date DATE, customer VARCHAR, sku VARCHAR, planner VARCHAR,
        event_type VARCHAR, adjustment_pct DOUBLE, comment VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS overrides (
        override_id VARCHAR PRIMARY KEY, dataset_version VARCHAR, customer VARCHAR, sku VARCHAR, date DATE,
        event_type VARCHAR, uplift_pct DOUBLE, comment VARCHAR, created_by VARCHAR, created_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS forecast_runs (
        run_id VARCHAR PRIMARY KEY, created_at TIMESTAMP, finished_at TIMESTAMP, dataset_version VARCHAR,
        horizon INTEGER, model_version VARCHAR, scenario VARCHAR, status VARCHAR, duration_s DOUBLE,
        n_series INTEGER, n_models INTEGER, params_json VARCHAR, summary_json VARCHAR, message VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS series_selection (
        run_id VARCHAR, series_id VARCHAR, customer VARCHAR, sku VARCHAR, history_months INTEGER,
        series_type VARCHAR, champion VARCHAR, challenger VARCHAR, wmape DOUBLE, bias DOUBLE, rmse DOUBLE,
        mase DOUBLE, challenger_wmape DOUBLE, wmape_std DOUBLE, confidence VARCHAR, confidence_score INTEGER,
        candidates VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS series_profiles (
        run_id VARCHAR, series_id VARCHAR, customer VARCHAR, sku VARCHAR, n_obs INTEGER, mean DOUBLE,
        median DOUBLE, variance DOUBLE, cv DOUBLE, zero_pct DOUBLE, adi DOUBLE, cv2 DOUBLE,
        trend_strength DOUBLE, seasonal_strength DOUBLE, trend_slope_pct DOUBLE, residual_cv DOUBLE,
        promo_lift DOUBLE, promo_corr DOUBLE, distribution_corr DOUBLE, distribution_range DOUBLE,
        structural_break BOOLEAN, break_index INTEGER, break_shift_pct DOUBLE, series_type VARCHAR,
        classification_reason VARCHAR, intermittency VARCHAR, candidate_models VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS model_registry (
        run_id VARCHAR, series_id VARCHAR, model VARCHAR, model_version VARCHAR, training_date TIMESTAMP,
        data_cutoff DATE, status VARCHAR, wmape DOUBLE, bias DOUBLE, mae DOUBLE, rmse DOUBLE, mape DOUBLE,
        smape DOUBLE, mase DOUBLE, wmape_std DOUBLE, n_folds INTEGER, fold_wmape VARCHAR, rank INTEGER,
        parameters VARCHAR, champion_flag BOOLEAN, challenger_flag BOOLEAN)""",
    """CREATE TABLE IF NOT EXISTS backtest_results (
        run_id VARCHAR, series_id VARCHAR, model VARCHAR, fold INTEGER, origin DATE, date DATE,
        horizon_step INTEGER, actual DOUBLE, forecast DOUBLE)""",
    """CREATE TABLE IF NOT EXISTS forecasts (
        run_id VARCHAR, series_id VARCHAR, date DATE, model VARCHAR, role VARCHAR, p50 DOUBLE, sigma DOUBLE,
        p10 DOUBLE, p90 DOUBLE)""",
    """CREATE TABLE IF NOT EXISTS scenarios (
        scenario_id VARCHAR PRIMARY KEY, name VARCHAR, kind VARCHAR, description VARCHAR, params_json VARCHAR,
        is_system BOOLEAN, created_at TIMESTAMP, updated_at TIMESTAMP)""",
]

_lock = threading.RLock()
_conn: duckdb.DuckDBPyConnection | None = None
_db_path: Path | None = None


def connect(path: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    """(Re)open the database. ``":memory:"`` is supported for tests."""
    global _conn, _db_path
    with _lock:
        if _conn is not None:
            _conn.close()
        target = str(path or settings.db_path)
        if target != ":memory:":
            Path(target).parent.mkdir(parents=True, exist_ok=True)
        _conn = duckdb.connect(target)
        _db_path = Path(target) if target != ":memory:" else None
        for ddl in SCHEMA:
            _conn.execute(ddl)
        return _conn


def get_conn() -> duckdb.DuckDBPyConnection:
    return _conn if _conn is not None else connect()


@contextmanager
def locked() -> Iterator[duckdb.DuckDBPyConnection]:
    with _lock:
        yield get_conn()


def query_df(sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> pd.DataFrame:
    with locked() as con:
        return con.execute(sql, params or []).df()


def execute(sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> None:
    with locked() as con:
        con.execute(sql, params or [])


def scalar(sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> Any:
    with locked() as con:
        row = con.execute(sql, params or []).fetchone()
        return row[0] if row else None


def insert_df(table: str, df: pd.DataFrame) -> None:
    """Append a DataFrame by column name (missing table columns become NULL)."""
    if df is None or df.empty:
        return
    with locked() as con:
        cols = [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]
        use = [c for c in cols if c in df.columns]
        con.register("_insert_df", df[use])
        try:
            col_sql = ", ".join(f'"{c}"' for c in use)
            con.execute(f"INSERT INTO {table} ({col_sql}) SELECT {col_sql} FROM _insert_df")
        finally:
            con.unregister("_insert_df")


def get_state(key: str, default: str | None = None) -> str | None:
    v = scalar("SELECT value FROM app_state WHERE key = ?", [key])
    return default if v is None else str(v)


def set_state(key: str, value: str | None) -> None:
    with locked() as con:
        con.execute("DELETE FROM app_state WHERE key = ?", [key])
        if value is not None:
            con.execute("INSERT INTO app_state VALUES (?, ?)", [key, value])
