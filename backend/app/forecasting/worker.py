"""Per-series pipeline: profile -> route -> backtest -> rank -> forecast.

Kept free of FastAPI/DB imports so it can run in worker processes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.backtesting.rolling import clean_stockouts, make_folds, run_backtest
from app.metrics import all_metrics
from app.model_selection import ModelEvaluation, model_confidence, rank_models, select_champion

from .models import MODEL_REGISTRY
from .panel import SeriesInput
from .profiling import profile_series
from .router import candidate_models

Z90 = 1.2815515655446004  # P10/P90 quantile of the standard normal


@dataclass
class RunParams:
    horizon: int = 12
    n_folds: int = 4
    fold_horizon: int = 3
    clean_stockouts: bool = True
    run_all_models: bool = False
    models: list[str] = field(default_factory=list)


def _interval_sigma(bt_actual: np.ndarray, bt_forecast: np.ndarray, y: np.ndarray) -> float:
    if bt_actual.size:
        return float(np.sqrt(np.mean((bt_forecast - bt_actual) ** 2)))
    tail = y[-12:]
    return float(tail.std(ddof=1)) if tail.size > 1 else float(abs(y[-1]) * 0.25 if y.size else 0.0)


def process_series(s: SeriesInput, params: RunParams) -> dict[str, Any]:
    promo = s.X["promotion"].to_numpy() if "promotion" in s.X else None
    dist = s.X["distribution"].to_numpy() if "distribution" in s.X else None
    profile = profile_series(s.y, promo, dist)
    candidates = candidate_models(profile["series_type"], params.run_all_models, params.models or None)
    folds = make_folds(len(s.y), params.n_folds, params.fold_horizon, min_train=12)
    min_train = min((f.train_end for f in folds), default=0)

    evals: list[ModelEvaluation] = []
    backtests: dict[str, Any] = {}
    for name in candidates:
        model = MODEL_REGISTRY[name]
        if not folds:
            evals.append(ModelEvaluation(name, math.nan, math.nan, math.nan, status="no_backtest"))
            continue
        if min_train < model.min_obs:
            evals.append(
                ModelEvaluation(
                    name, math.nan, math.nan, math.nan, status="insufficient_history", params={"min_obs": model.min_obs}
                )
            )
            continue
        try:
            bt = run_backtest(model, s.y, s.X, folds, s.stockout, params.clean_stockouts)
        except Exception as exc:
            evals.append(
                ModelEvaluation(name, math.nan, math.nan, math.nan, status="failed", params={"error": str(exc)[:200]})
            )
            continue
        m = all_metrics(bt.actual, bt.forecast, insample=s.y[: folds[0].train_end])
        evals.append(
            ModelEvaluation(
                name,
                m["wmape"],
                m["bias"],
                m["rmse"],
                mae=m["mae"],
                mape=m["mape"],
                smape=m["smape"],
                mase=m["mase"],
                fold_wmape=bt.fold_wmape,
                params=bt.params,
            )
        )
        backtests[name] = bt

    evals = rank_models(evals)
    champion, challenger = select_champion(evals)
    champ_name = champion.model if champion else "Naive"
    confidence, conf_score, conf_parts = model_confidence(champion, challenger, len(s.y))

    y_fit = clean_stockouts(s.y, s.stockout) if params.clean_stockouts else s.y
    forecasts: list[dict[str, Any]] = []
    final_params: dict[str, Any] = {}
    roles = [("champion", champ_name)] + ([("challenger", challenger.model)] if challenger else [])
    for role, name in roles:
        out = MODEL_REGISTRY[name].forecast(y_fit, params.horizon, s.X, s.X_future)
        bt = backtests.get(name)
        sigma1 = (
            _interval_sigma(bt.actual, bt.forecast, s.y)
            if bt is not None
            else _interval_sigma(np.array([]), np.array([]), s.y)
        )
        h_bar = float(np.mean(bt.step)) if bt is not None and bt.step else 1.0
        final_params[name] = out.params
        for k, (d, p50) in enumerate(zip(s.future_dates, out.mean, strict=True), start=1):
            sigma = sigma1 * math.sqrt(k / h_bar)
            forecasts.append(
                {
                    "date": d,
                    "model": name,
                    "role": role,
                    "p50": float(p50),
                    "sigma": float(sigma),
                    "p10": float(max(0.0, p50 - Z90 * sigma)),
                    "p90": float(p50 + Z90 * sigma),
                }
            )

    registry = []
    for e in evals:
        registry.append(
            {
                "model": e.model,
                "status": e.status,
                "wmape": e.wmape,
                "bias": e.bias,
                "mae": e.mae,
                "rmse": e.rmse,
                "mape": e.mape,
                "smape": e.smape,
                "mase": e.mase,
                "wmape_std": e.wmape_std,
                "n_folds": len(e.fold_wmape),
                "fold_wmape": e.fold_wmape,
                "rank": e.rank,
                "parameters": final_params.get(e.model, e.params),
                "champion_flag": e.model == champ_name and e.rank == 1,
                "challenger_flag": challenger is not None and e.model == challenger.model,
            }
        )

    bt_rows = []
    for name, bt in backtests.items():
        for fold, idx, step, a, f in zip(bt.fold, bt.index, bt.step, bt.actual, bt.forecast, strict=True):
            bt_rows.append(
                {
                    "model": name,
                    "fold": fold,
                    "origin": s.dates[idx - step],  # last month of the training window
                    "date": s.dates[idx],
                    "horizon_step": step,
                    "actual": float(a),
                    "forecast": float(f),
                }
            )

    profile_clean = {k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in profile.items()}
    return {
        "series_id": s.series_id,
        "customer": s.customer,
        "sku": s.sku,
        "history_months": len(s.y),
        "profile": profile_clean,
        "candidates": candidates,
        "champion": champ_name,
        "challenger": challenger.model if challenger else None,
        "wmape": champion.wmape if champion else math.nan,
        "bias": champion.bias if champion else math.nan,
        "rmse": champion.rmse if champion else math.nan,
        "mase": champion.mase if champion else math.nan,
        "challenger_wmape": challenger.wmape if challenger else math.nan,
        "wmape_std": champion.wmape_std if champion else math.nan,
        "confidence": confidence,
        "confidence_score": conf_score,
        "confidence_parts": conf_parts,
        "registry": registry,
        "backtest": bt_rows,
        "forecasts": forecasts,
    }


def process_series_safe(s: SeriesInput, params: RunParams) -> dict[str, Any]:
    """Never raises: a broken series falls back to a Naive forecast."""
    try:
        return process_series(s, params)
    except Exception as exc:
        fallback = RunParams(params.horizon, 0, params.fold_horizon, params.clean_stockouts, False, ["Naive"])
        res = process_series(s, fallback)
        res["error"] = str(exc)[:300]
        return res
