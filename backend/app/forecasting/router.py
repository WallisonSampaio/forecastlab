"""Model Candidate Router: only plausible models compete for each series.

Routing keeps run time low and avoids nonsense matches (e.g. SARIMA on an
intermittent series). Naive is always kept as the benchmark that every
model must beat (and that FVA compares against).
"""

from __future__ import annotations

from .models import MODEL_REGISTRY

ROUTES: dict[str, list[str]] = {
    "Inactive": ["Naive", "Moving Average"],
    "Short History": ["Naive", "Moving Average", "SES", "Holt", "ETS"],
    "Intermittent": ["Croston", "SBA", "TSB", "Moving Average", "Naive"],
    "Seasonal": ["Seasonal Naive", "Holt-Winters", "ETS", "SARIMA", "Regression", "Naive"],
    "Trending": ["Holt", "ETS", "ARIMA", "Regression", "Seasonal Naive", "Naive"],
    "Declining": ["Holt", "ETS", "ARIMA", "Regression", "Seasonal Naive", "Naive"],
    "Promo Driven": ["Regression", "Random Forest", "Gradient Boosting", "ETS", "Seasonal Naive", "Naive"],
    "Distribution Driven": ["Regression", "Gradient Boosting", "Holt", "ETS", "Naive"],
    "Structural Change": ["Naive", "SES", "Holt", "ETS", "ARIMA", "Moving Average"],
    "Volatile": ["Moving Average", "SES", "ETS", "Random Forest", "Gradient Boosting", "Seasonal Naive", "Naive"],
    "Stable": ["SES", "Moving Average", "ETS", "ARIMA", "Regression", "Seasonal Naive", "Naive"],
}


def candidate_models(series_type: str, run_all: bool = False, allowed: list[str] | None = None) -> list[str]:
    """Candidate list for a series type.

    Driver-based models still run without driver columns (they fall back to
    trend + calendar features), so they are never excluded here.
    """
    names = list(MODEL_REGISTRY) if run_all else list(ROUTES.get(series_type, ROUTES["Stable"]))
    if "Naive" not in names:
        names.append("Naive")
    return [n for n in names if not allowed or n in allowed or n == "Naive"]
