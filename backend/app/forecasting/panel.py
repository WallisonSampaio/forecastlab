"""Turns the long sales table into per-series model inputs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from synthetic_data_generator.calendar import month_features

from .design import baseline_design
from .models import DRIVER_COLUMNS

SERIES_SEP = "|"


def series_id(customer: str, sku: str) -> str:
    return f"{customer}{SERIES_SEP}{sku}"


@dataclass
class SeriesInput:
    series_id: str
    customer: str
    sku: str
    dates: pd.DatetimeIndex
    y: np.ndarray
    X: pd.DataFrame
    X_future: pd.DataFrame
    future_dates: pd.DatetimeIndex
    stockout: np.ndarray | None
    drivers: list[str]


def available_drivers(sales: pd.DataFrame) -> list[str]:
    return [
        c
        for c in DRIVER_COLUMNS
        if c in sales.columns and sales[c].notna().any() and float(sales[c].fillna(0).abs().sum()) > 0
    ]


def holidays_for(dates: pd.DatetimeIndex) -> np.ndarray:
    return np.array([int(month_features(d.year, d.month)["holidays"]) for d in dates], dtype=float)


def calendar_frame(dates: pd.DatetimeIndex, t0: int, with_holiday: bool) -> pd.DataFrame:
    cal = pd.DataFrame({"t": np.arange(t0, t0 + len(dates)), "month": dates.month}, index=dates)
    if with_holiday:
        cal["holiday"] = holidays_for(dates)
    return cal


def build_panel(sales: pd.DataFrame, horizon: int) -> list[SeriesInput]:
    """One SeriesInput per Customer x SKU.

    Each series runs from its first record to the dataset end; missing months
    are real zero-demand months (sales extracts omit them).
    """
    sales = sales.copy()
    sales["date"] = pd.to_datetime(sales["date"]).dt.to_period("M").dt.to_timestamp()
    end = sales["date"].max()
    future_dates = pd.date_range(end + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    drivers = available_drivers(sales)
    agg: dict[str, str] = {"units": "sum"}
    for c in drivers + (["stockout"] if "stockout" in sales.columns else []):
        if c == "marketing_investment":
            agg[c] = "sum"
        elif c in ("promotion", "merchandising_event", "stockout", "holiday"):
            agg[c] = "max"
        else:
            agg[c] = "mean"
    monthly = sales.groupby(["customer", "sku", "date"], sort=True).agg(agg)
    all_months = pd.date_range(sales["date"].min(), end, freq="MS")
    hol_all = pd.Series(holidays_for(all_months), index=all_months)
    has_hol = "holiday" in drivers
    future_cal = calendar_frame(future_dates, 0, has_hol)

    out: list[SeriesInput] = []
    for (cust, sku), g in monthly.groupby(level=[0, 1], sort=True):
        g = g.droplevel([0, 1])
        idx = pd.date_range(g.index.min(), end, freq="MS")
        g = g.reindex(idx)
        y = g["units"].fillna(0.0).clip(lower=0).to_numpy(float)
        X = pd.DataFrame({"t": np.arange(len(idx)), "month": idx.month}, index=idx)
        for c in drivers:
            col = g[c]
            if c == "price":
                col = col.replace(0, np.nan).ffill().bfill().fillna(0.0)
            elif c == "distribution":
                col = col.ffill().fillna(0.0)
            elif c == "holiday":
                col = hol_all.reindex(idx)
            else:
                col = col.fillna(0.0)
            X[c] = col.to_numpy(float)
        cal = future_cal.copy()
        cal["t"] = np.arange(len(idx), len(idx) + horizon)
        out.append(
            SeriesInput(
                series_id=series_id(str(cust), str(sku)),
                customer=str(cust),
                sku=str(sku),
                dates=idx,
                y=y,
                X=X,
                X_future=baseline_design(X, cal),
                future_dates=future_dates,
                stockout=g["stockout"].fillna(0).to_numpy(float) if "stockout" in g else None,
                drivers=drivers,
            )
        )
    return out
