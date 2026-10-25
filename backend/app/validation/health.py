"""Dataset Health Check, Data Quality Score and execution blocking.

Severity levels
---------------
* critical - the forecast run is blocked until the file is fixed
* warning  - the data is usable; the issue is reported and handled
* info     - informational (e.g. daily data aggregated to monthly)
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from app.ingestion.schema import NUMERIC, OPTIONAL, REQUIRED, map_columns

MIN_HISTORY_FOR_FORECAST = 6
SHORT_HISTORY = 12
MAX_EXAMPLES = 5


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    count: int = 0
    examples: list[Any] = field(default_factory=list)


@dataclass
class ValidationReport:
    status: str
    can_forecast: bool
    summary: dict[str, Any]
    quality: dict[str, float]
    issues: list[Issue]
    column_mapping: dict[str, str]
    missing_optional: list[str]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["blocking_message"] = (
            None if self.can_forecast else "Forecast execution blocked. Fix the critical issues listed below."
        )
        return d


def _examples(df: pd.DataFrame, mask: pd.Series, cols: list[str]) -> list[dict[str, Any]]:
    rows = df.loc[mask, [c for c in cols if c in df.columns]].head(MAX_EXAMPLES)
    out = []
    for idx, r in rows.iterrows():
        item = {"row": int(idx) + 2}  # +2: header row + 1-based (spreadsheet line number)
        item.update({k: (None if pd.isna(v) else str(v)) for k, v in r.items()})
        out.append(item)
    return out


def _parse_dates(s: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    parsed = pd.to_datetime(s, errors="coerce", format="mixed", dayfirst=False)
    # Retry day-first for strings like 31/01/2024 that failed month-first parsing.
    retry = parsed.isna() & s.notna()
    if retry.any():
        parsed.loc[retry] = pd.to_datetime(s[retry], errors="coerce", format="mixed", dayfirst=True)
    return parsed


def validate_and_normalize(raw: pd.DataFrame) -> tuple[ValidationReport, pd.DataFrame | None]:
    issues: list[Issue] = []
    mapping = map_columns(list(raw.columns))
    df = raw.rename(columns=mapping)[list(mapping.values())].copy()
    missing_req = [c for c in REQUIRED if c not in df.columns]
    missing_opt = [c for c in OPTIONAL if c not in df.columns]
    n_rows = len(df)

    if missing_req:
        issues.append(
            Issue(
                "critical",
                "missing_columns",
                f"Missing required column(s): {', '.join(missing_req)}",
                len(missing_req),
                missing_req,
            )
        )
    if n_rows == 0:
        issues.append(Issue("critical", "empty", "The file has no data rows."))
    if missing_req or n_rows == 0:
        report = ValidationReport(
            "blocked", False, {"rows": n_rows}, _quality(0, 0, 0, 0), issues, mapping, missing_opt
        )
        return report, None

    # ---- missing values -------------------------------------------------------------
    missing_values = {c: int(df[c].isna().sum()) for c in df.columns}
    for c in ("date", "customer", "sku", "region", "channel"):
        n = missing_values.get(c, 0)
        if n:
            issues.append(
                Issue(
                    "critical",
                    f"missing_{c}",
                    f"{n} row(s) without {c}",
                    n,
                    _examples(raw.rename(columns=mapping), df[c].isna(), REQUIRED),
                )
            )

    # ---- dates ------------------------------------------------------------------------
    parsed = _parse_dates(df["date"])
    invalid_dates = parsed.isna() & df["date"].notna()
    n_invalid_dates = int(invalid_dates.sum())
    if n_invalid_dates:
        issues.append(
            Issue(
                "critical",
                "invalid_dates",
                f"{n_invalid_dates} row(s) with an invalid date",
                n_invalid_dates,
                _examples(df, invalid_dates, ["date", "customer", "sku"]),
            )
        )
    df["date"] = parsed.dt.to_period("M").dt.to_timestamp()
    future_mask = df["date"] > pd.Timestamp.today().normalize()
    if future_mask.any():
        issues.append(
            Issue(
                "warning",
                "future_dates",
                f"{int(future_mask.sum())} row(s) dated in the future",
                int(future_mask.sum()),
                _examples(df, future_mask, ["date", "customer", "sku"]),
            )
        )

    # ---- numeric columns -----------------------------------------------------------------
    for c in [c for c in NUMERIC if c in df.columns]:
        original = df[c]
        conv = pd.to_numeric(original, errors="coerce")
        bad = conv.isna() & original.notna()
        if bad.any():
            sev = "critical" if c == "units" else "warning"
            issues.append(
                Issue(
                    sev,
                    f"non_numeric_{c}",
                    f"{int(bad.sum())} non-numeric value(s) in {c}",
                    int(bad.sum()),
                    _examples(df, bad, ["date", "customer", "sku", c]),
                )
            )
        df[c] = conv
    units_missing = int(df["units"].isna().sum())
    if units_missing:
        sev = "critical" if units_missing / n_rows > 0.2 else "warning"
        issues.append(
            Issue(sev, "missing_units", f"{units_missing} row(s) without units (treated as 0)", units_missing)
        )
    neg_units = df["units"] < 0
    n_negative = int(neg_units.sum())
    if n_negative:
        issues.append(
            Issue(
                "critical",
                "negative_units",
                f"{n_negative} row(s) with negative units (returns must be netted before upload)",
                n_negative,
                _examples(df, neg_units, ["date", "customer", "sku", "units"]),
            )
        )
    for c in ("revenue", "price", "marketing_investment"):
        if c in df.columns and (df[c] < 0).any():
            n = int((df[c] < 0).sum())
            n_negative += n
            issues.append(Issue("warning", f"negative_{c}", f"{n} negative value(s) in {c}", n))
    if "distribution" in df.columns and ((df["distribution"] > 100) | (df["distribution"] < 0)).any():
        n = int(((df["distribution"] > 100) | (df["distribution"] < 0)).sum())
        issues.append(Issue("warning", "distribution_range", f"{n} distribution value(s) outside 0-100", n))

    # ---- duplicates & granularity ---------------------------------------------------------------
    dup_rows = int(raw.duplicated().sum())
    if dup_rows:
        issues.append(Issue("warning", "duplicated_rows", f"{dup_rows} fully duplicated row(s) (removed)", dup_rows))
    valid = df.drop_duplicates()
    valid = valid[valid["date"].notna() & valid["customer"].notna() & valid["sku"].notna()]
    key_dups = int(valid.duplicated(["date", "customer", "sku"]).sum())
    if key_dups:
        issues.append(
            Issue(
                "info",
                "aggregated_to_monthly",
                f"{key_dups} row(s) share the same Customer x SKU x Month and were aggregated",
                key_dups,
            )
        )

    norm = _aggregate_monthly(valid)

    # ---- series level checks -----------------------------------------------------------------
    end = norm["date"].max()
    hist = norm.groupby(["customer", "sku"])["date"].min()
    months = ((end.year - hist.dt.year) * 12 + (end.month - hist.dt.month) + 1).astype(int)
    n_series = len(months)
    expected_cells = int(months.sum())
    observed_nonzero = int((norm["units"] > 0).sum())
    zero_periods = max(0, expected_cells - observed_nonzero)
    short = int((months < SHORT_HISTORY).sum())
    if short:
        issues.append(
            Issue(
                "warning",
                "short_history",
                f"{short} series with less than {SHORT_HISTORY} months of history (short-history models will be used)",
                short,
            )
        )
    if months.max() < MIN_HISTORY_FOR_FORECAST:
        issues.append(
            Issue(
                "critical",
                "insufficient_history",
                f"At least {MIN_HISTORY_FOR_FORECAST} months of history are required (found {int(months.max())}).",
            )
        )
    if zero_periods:
        issues.append(
            Issue(
                "info",
                "zero_demand_periods",
                f"{zero_periods} series-month(s) with zero demand (missing months are treated as zero)",
                zero_periods,
            )
        )
    n_outliers, outlier_examples = _outliers(norm)
    if n_outliers:
        issues.append(
            Issue(
                "warning",
                "outliers",
                f"{n_outliers} unexplained outlier(s) (robust z-score > 5 after seasonality; promo/stock-out months excluded)",
                n_outliers,
                outlier_examples,
            )
        )
    if missing_opt:
        issues.append(
            Issue(
                "info",
                "optional_columns_missing",
                f"Optional columns not provided: {', '.join(missing_opt)}",
                len(missing_opt),
                missing_opt,
            )
        )

    # ---- quality score ------------------------------------------------------------------------
    used_cols = [c for c in df.columns]
    total_cells = n_rows * len(used_cols)
    completeness = 1 - sum(missing_values.values()) / total_cells if total_cells else 0.0
    consistency = 1 - min(1.0, (n_invalid_dates + n_negative + dup_rows) / max(n_rows, 1) * 5)
    depth = min(1.0, float(months.median()) / 48)
    hierarchy_cols = sum(c in df.columns for c in ("region", "channel", "category", "brand", "product"))
    granularity = 0.6 + 0.4 * hierarchy_cols / 5
    quality = _quality(completeness, consistency, depth, granularity)

    critical = any(i.severity == "critical" for i in issues)
    status = "blocked" if critical else ("warnings" if any(i.severity == "warning" for i in issues) else "valid")
    summary = {
        "rows": n_rows,
        "rows_after_aggregation": len(norm),
        "n_skus": int(norm["sku"].nunique()),
        "n_customers": int(norm["customer"].nunique()),
        "n_series": n_series,
        "start_date": norm["date"].min().strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "months": int((end.year - norm["date"].min().year) * 12 + end.month - norm["date"].min().month + 1),
        "missing_values": missing_values,
        "duplicated_rows": dup_rows,
        "invalid_dates": n_invalid_dates,
        "negative_values": n_negative,
        "zero_demand_periods": zero_periods,
        "outliers": n_outliers,
        "history": {
            "min_months": int(months.min()),
            "median_months": float(months.median()),
            "max_months": int(months.max()),
            "short_series": short,
        },
        "total_units": float(norm["units"].sum()),
        "total_revenue": float(norm["revenue"].sum()) if "revenue" in norm else None,
    }
    report = ValidationReport(status, not critical, summary, quality, issues, mapping, missing_opt)
    return report, (None if critical else norm)


def _quality(completeness: float, consistency: float, depth: float, granularity: float) -> dict[str, float]:
    overall = 0.35 * completeness + 0.30 * consistency + 0.20 * depth + 0.15 * granularity
    return {
        "completeness": round(100 * max(0.0, completeness), 1),
        "consistency": round(100 * max(0.0, consistency), 1),
        "historical_depth": round(100 * max(0.0, depth), 1),
        "granularity": round(100 * max(0.0, granularity), 1),
        "overall": round(100 * max(0.0, overall)),
    }


def _aggregate_monthly(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["units"] = df["units"].fillna(0.0)
    if "revenue" not in df.columns and "price" in df.columns:
        df["revenue"] = df["units"] * df["price"].fillna(0)
    agg: dict[str, Any] = {"units": "sum"}
    first = ["region", "channel", "customer_location", "product", "category", "brand"]
    for c in first:
        if c in df.columns:
            agg[c] = "first"
    for c, how in {
        "revenue": "sum",
        "price": "mean",
        "promotion": "max",
        "distribution": "mean",
        "stockout": "max",
        "holiday": "max",
        "marketing_investment": "sum",
        "merchandising_event": "max",
        "customer_potential": "max",
    }.items():
        if c in df.columns:
            agg[c] = how
    out = df.groupby(["date", "customer", "sku"], as_index=False).agg(agg)
    if "revenue" in out.columns and "price" in out.columns:
        derived = out["revenue"] / out["units"].replace(0, np.nan)
        out["price"] = out["price"].fillna(derived)
    elif "revenue" in out.columns:
        out["price"] = out["revenue"] / out["units"].replace(0, np.nan)
    out["customer_location"] = out.get("customer_location", out["customer"]).fillna(out["customer"])
    out["product"] = out.get("product", out["sku"]).fillna(out["sku"])
    out["category"] = out.get("category", pd.Series("Uncategorized", index=out.index)).fillna("Uncategorized")
    out["brand"] = out.get("brand", pd.Series("Unbranded", index=out.index)).fillna("Unbranded")
    for c in ("customer", "sku", "region", "channel", "customer_location", "product", "category", "brand"):
        out[c] = out[c].astype(str).str.strip()
    return out.sort_values(["customer", "sku", "date"]).reset_index(drop=True)


def _outliers(norm: pd.DataFrame) -> tuple[int, list[dict[str, Any]]]:
    """Unexplained spikes/drops: robust z-score of the seasonally adjusted, locally detrended log demand.

    Months explained by a promotion, merchandising event or stock-out are not flagged.
    """
    examples: list[tuple[float, dict[str, Any]]] = []
    count = 0
    explained_cols = [c for c in ("promotion", "merchandising_event", "stockout") if c in norm.columns]
    for (cust, sku), g in norm.groupby(["customer", "sku"]):
        u = g["units"].to_numpy(float)
        if u.size < 12 or (u > 0).mean() < 0.7:  # intermittent series: spikes are the pattern
            continue
        lu = np.log1p(u)
        months = g["date"].dt.month.to_numpy()
        season = np.zeros_like(lu)
        if u.size >= 24:
            dev = lu - pd.Series(lu).rolling(12, center=True, min_periods=6).mean().to_numpy()
            by_month = pd.Series(dev).groupby(months).mean()
            season = by_month.reindex(months).fillna(0).to_numpy()
        adj = lu - season
        local = pd.Series(adj).rolling(7, center=True, min_periods=3).median().to_numpy()
        resid = adj - local
        mad = np.median(np.abs(resid - np.median(resid)))
        if mad == 0:
            continue
        z = 0.6745 * (resid - np.median(resid)) / mad
        explained = g[explained_cols].fillna(0).sum(axis=1).to_numpy() > 0 if explained_cols else np.zeros(u.size, bool)
        idx = np.flatnonzero((np.abs(z) > 5) & ~explained)
        count += idx.size
        for i in idx:
            examples.append(
                (
                    abs(float(z[i])),
                    {
                        "customer": cust,
                        "sku": sku,
                        "date": g["date"].iloc[i].strftime("%Y-%m"),
                        "units": float(u[i]),
                        "z_score": round(float(z[i]), 1),
                    },
                )
            )
    examples.sort(key=lambda x: -x[0])
    return count, [e for _, e in examples[:MAX_EXAMPLES]]


def score_label(score: float) -> str:
    if score is None or (isinstance(score, float) and math.isnan(score)):
        return "n/a"
    return "Excellent" if score >= 90 else "Good" if score >= 75 else "Fair" if score >= 60 else "Poor"
