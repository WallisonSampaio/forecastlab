"""Forecast model zoo.

Every model exposes the same stateless interface so that backtesting,
model routing and the final forecast treat them identically:

    model.forecast(y_train, h, X_train, X_future) -> ModelOutput

* ``y_train``  - history only (the backtester never passes future actuals).
* ``X_train``  - calendar/driver design aligned with ``y_train`` (columns
  ``t``, ``month`` and optional drivers).
* ``X_future`` - the same design for the forecast window. Drivers in the
  future window are *planned* values (price list, promo calendar,
  distribution plan); they never contain the target.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

MODEL_FRAMEWORK_VERSION = "1.0"
SEASON = 12
DRIVER_COLUMNS = ["promotion", "price", "distribution", "merchandising_event", "marketing_investment", "holiday"]


@dataclass
class ModelOutput:
    mean: np.ndarray
    params: dict[str, Any] = field(default_factory=dict)


class BaseModel:
    name = "Base"
    family = "Baseline"
    description = ""
    min_obs = 2
    uses_drivers = False

    @property
    def version(self) -> str:
        return f"{self.name.lower().replace(' ', '-')}-{MODEL_FRAMEWORK_VERSION}"

    def forecast(
        self,
        y: np.ndarray,
        h: int,
        X_train: pd.DataFrame | None = None,
        X_future: pd.DataFrame | None = None,
    ) -> ModelOutput:
        y = np.asarray(y, dtype=float)
        if X_future is not None and "units" in X_future.columns:  # defensive leakage guard
            raise ValueError("X_future must not contain the target column")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out = self._forecast(y, h, X_train, X_future)
        mean = np.asarray(out.mean, dtype=float)[:h]
        if mean.size < h:
            mean = np.r_[mean, np.repeat(mean[-1] if mean.size else 0.0, h - mean.size)]
        out.mean = np.clip(np.nan_to_num(mean, nan=0.0, posinf=0.0, neginf=0.0), 0, None)
        return out

    def _forecast(self, y, h, X_train, X_future) -> ModelOutput:  # pragma: no cover - abstract
        raise NotImplementedError


# --------------------------------------------------------------------------- baselines
class Naive(BaseModel):
    name = "Naive"
    description = "Last observed value carried forward."
    min_obs = 1

    def _forecast(self, y, h, X_train, X_future):
        return ModelOutput(np.repeat(y[-1], h))


class SeasonalNaive(BaseModel):
    name = "Seasonal Naive"
    description = "Same month of the previous year."
    min_obs = SEASON

    def _forecast(self, y, h, X_train, X_future):
        idx = len(y) - SEASON + (np.arange(h) % SEASON)
        return ModelOutput(y[idx], {"season": SEASON})


class MovingAverage(BaseModel):
    name = "Moving Average"
    description = "Average of the last k months."
    min_obs = 3

    def __init__(self, window: int = 3):
        self.window = window

    def _forecast(self, y, h, X_train, X_future):
        k = min(self.window, len(y))
        return ModelOutput(np.repeat(y[-k:].mean(), h), {"window": k})


# --------------------------------------------------------------------- exponential smoothing
class SES(BaseModel):
    name = "SES"
    family = "Exponential Smoothing"
    description = "Simple exponential smoothing (level only)."
    min_obs = 6

    def _forecast(self, y, h, X_train, X_future):
        from statsmodels.tsa.holtwinters import SimpleExpSmoothing

        fit = SimpleExpSmoothing(y, initialization_method="estimated").fit(use_brute=False)
        return ModelOutput(fit.forecast(h), {"alpha": round(float(fit.params["smoothing_level"]), 4)})


class Holt(BaseModel):
    name = "Holt"
    family = "Exponential Smoothing"
    description = "Holt's linear trend method with damped trend."
    min_obs = 10

    def _forecast(self, y, h, X_train, X_future):
        from statsmodels.tsa.holtwinters import Holt as _Holt

        fit = _Holt(y, damped_trend=True, initialization_method="estimated").fit(use_brute=False)
        p = fit.params
        return ModelOutput(
            fit.forecast(h),
            {
                "alpha": round(float(p["smoothing_level"]), 4),
                "beta": round(float(p["smoothing_trend"]), 4),
                "phi": round(float(p["damping_trend"]), 4),
            },
        )


class HoltWinters(BaseModel):
    name = "Holt-Winters"
    family = "Exponential Smoothing"
    description = "Additive damped trend with additive/multiplicative seasonality."
    min_obs = 2 * SEASON

    def _forecast(self, y, h, X_train, X_future):
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        seasonal = "mul" if y.min() > 0 else "add"
        fit = ExponentialSmoothing(
            y,
            trend="add",
            damped_trend=True,
            seasonal=seasonal,
            seasonal_periods=SEASON,
            initialization_method="estimated",
        ).fit(use_brute=False)
        return ModelOutput(fit.forecast(h), {"trend": "add_damped", "seasonal": seasonal})


class ETS(BaseModel):
    name = "ETS"
    family = "Exponential Smoothing"
    description = "Automatic ETS: best trend/season combination by AICc, then refined."
    min_obs = 8

    def _forecast(self, y, h, X_train, X_future):
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        def build(trend, seasonal, init):
            return ExponentialSmoothing(
                y,
                trend=trend,
                damped_trend=trend is not None,
                seasonal=seasonal,
                seasonal_periods=SEASON if seasonal else None,
                initialization_method=init,
            )

        configs: list[tuple[str | None, str | None]] = [(None, None), ("add", None)]
        if len(y) >= 2 * SEASON:
            configs += [(None, "add"), ("add", "add")]
            if y.min() > 0:
                configs += [(None, "mul"), ("add", "mul")]
        # Fast screening with heuristic initial states, then one refined fit.
        best = None
        for trend, seasonal in configs:
            init = "heuristic" if seasonal and len(y) >= 10 + SEASON else "estimated"
            try:
                fit = build(trend, seasonal, init).fit(use_brute=False)
            except Exception:
                continue
            score = fit.aicc if np.isfinite(fit.aicc) else math.inf
            if best is None or score < best[0]:
                best = (score, fit, trend, seasonal)
        if best is None:
            raise RuntimeError("no ETS configuration converged")
        score, fit, trend, seasonal = best
        try:
            fit = build(trend, seasonal, "estimated").fit(use_brute=False)
        except Exception:
            pass
        code = f"ETS(A,{'Ad' if trend else 'N'},{({'add': 'A', 'mul': 'M'}).get(seasonal or '', 'N')})"
        return ModelOutput(fit.forecast(h), {"spec": code, "aicc": round(float(score), 2)})


# --------------------------------------------------------------------------- ARIMA family
class ARIMA(BaseModel):
    name = "ARIMA"
    family = "ARIMA"
    description = "ARIMA(1,1,1); drift included when the mean change is significant (|t| > 2)."
    min_obs = 12

    def _forecast(self, y, h, X_train, X_future):
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        d = np.diff(y)
        t_stat = d.mean() / (d.std(ddof=1) / math.sqrt(len(d))) if len(d) > 2 and d.std(ddof=1) > 0 else 0.0
        drift = abs(t_stat) > 2
        fit = SARIMAX(
            y,
            order=(1, 1, 1),
            trend="t" if drift else "n",
            enforce_stationarity=False,
            enforce_invertibility=False,
            concentrate_scale=True,
        ).fit(disp=False, maxiter=60)
        return ModelOutput(fit.forecast(h), {"order": "(1,1,1)", "drift": bool(drift)})


class SARIMA(BaseModel):
    name = "SARIMA"
    family = "ARIMA"
    description = "Seasonal 'airline' model SARIMA(0,1,1)(0,1,1)12 on log scale."
    min_obs = 3 * SEASON

    def _forecast(self, y, h, X_train, X_future):
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        z = np.log1p(y)
        fit = SARIMAX(
            z,
            order=(0, 1, 1),
            seasonal_order=(0, 1, 1, SEASON),
            enforce_stationarity=False,
            enforce_invertibility=False,
            concentrate_scale=True,
        ).fit(disp=False, maxiter=60)
        return ModelOutput(np.expm1(fit.forecast(h)), {"order": "(0,1,1)(0,1,1)12", "transform": "log1p"})


# ----------------------------------------------------------------------- intermittent demand
def _croston_core(y: np.ndarray, alpha: float) -> tuple[float, float]:
    nz = np.flatnonzero(y > 0)
    if nz.size == 0:
        return 0.0, 1.0
    z = float(y[nz[0]])
    p = float(np.diff(nz[:2])[0]) if nz.size > 1 else float(nz[0] + 1)
    q = 1
    for t in range(nz[0] + 1, len(y)):
        if y[t] > 0:
            z += alpha * (y[t] - z)
            p += alpha * (q - p)
            q = 1
        else:
            q += 1
    return z, max(p, 1.0)


class Croston(BaseModel):
    name = "Croston"
    family = "Intermittent"
    description = "Croston's method: separate smoothing of demand size and interval."
    min_obs = 6
    alpha = 0.1

    def _forecast(self, y, h, X_train, X_future):
        z, p = _croston_core(y, self.alpha)
        return ModelOutput(np.repeat(z / p, h), {"alpha": self.alpha, "size": round(z, 2), "interval": round(p, 2)})


class SBA(Croston):
    name = "SBA"
    description = "Syntetos-Boylan Approximation (bias-corrected Croston)."

    def _forecast(self, y, h, X_train, X_future):
        z, p = _croston_core(y, self.alpha)
        return ModelOutput(np.repeat((1 - self.alpha / 2) * z / p, h), {"alpha": self.alpha})


class TSB(BaseModel):
    name = "TSB"
    family = "Intermittent"
    description = "Teunter-Syntetos-Babai: smooths demand probability every period (handles obsolescence)."
    min_obs = 6
    alpha = 0.1
    beta = 0.1

    def _forecast(self, y, h, X_train, X_future):
        nz = y > 0
        if not nz.any():
            return ModelOutput(np.zeros(h))
        prob = float(nz[: min(len(y), SEASON)].mean()) or 0.1
        z = float(y[nz][0])
        for t in range(len(y)):
            if y[t] > 0:
                prob += self.beta * (1 - prob)
                z += self.alpha * (y[t] - z)
            else:
                prob += self.beta * (0 - prob)
        return ModelOutput(np.repeat(prob * z, h), {"alpha": self.alpha, "beta": self.beta, "prob": round(prob, 3)})


# ----------------------------------------------------------------------- driver-based models
def _driver_block(X: pd.DataFrame, ref: dict[str, float]) -> dict[str, np.ndarray]:
    cols: dict[str, np.ndarray] = {}
    if "promotion" in X:
        cols["promotion"] = X["promotion"].to_numpy(float)
    if "merchandising_event" in X:
        cols["merchandising"] = X["merchandising_event"].to_numpy(float)
    if "price" in X and ref.get("price", 0) > 0:
        cols["log_price"] = np.log(np.clip(X["price"].to_numpy(float), 1e-6, None) / ref["price"])
    if "distribution" in X and ref.get("distribution", 0) > 0:
        cols["log_distribution"] = np.log(np.clip(X["distribution"].to_numpy(float), 1.0, None) / ref["distribution"])
    if "marketing_investment" in X:
        cols["log_marketing"] = np.log1p(np.clip(X["marketing_investment"].to_numpy(float), 0, None))
    if "holiday" in X:
        cols["holiday"] = X["holiday"].to_numpy(float)
    return cols


def _refs(X_train: pd.DataFrame) -> dict[str, float]:
    ref: dict[str, float] = {}
    for c in ("price", "distribution"):
        if c in X_train:
            v = X_train[c].to_numpy(float)
            v = v[v > 0]
            ref[c] = float(np.median(v)) if v.size else 0.0
    return ref


class Regression(BaseModel):
    name = "Regression"
    family = "Regression"
    description = "Ridge regression on log demand: trend + month seasonality + promotion, price, distribution, merchandising, marketing, holidays."
    min_obs = 18
    uses_drivers = True
    ridge = 1.0

    def _design(self, X: pd.DataFrame, ref: dict[str, float], seasonal: bool) -> tuple[np.ndarray, list[str]]:
        cols: dict[str, np.ndarray] = {"trend": X["t"].to_numpy(float) / SEASON}
        m = X["month"].to_numpy(int)
        if seasonal:
            for k in range(2, 13):
                cols[f"m{k:02d}"] = (m == k).astype(float)
        else:
            cols["m_sin"] = np.sin(2 * np.pi * m / 12)
            cols["m_cos"] = np.cos(2 * np.pi * m / 12)
        cols.update(_driver_block(X, ref))
        names = list(cols)
        return np.column_stack([cols[n] for n in names]), names

    def _forecast(self, y, h, X_train, X_future):
        if X_train is None or X_future is None:
            raise ValueError("Regression requires a calendar/driver design")
        ref = _refs(X_train)
        seasonal = len(y) >= 2 * SEASON
        A, names = self._design(X_train, ref, seasonal)
        B, _ = self._design(X_future, ref, seasonal)
        mu, sd = A.mean(axis=0), A.std(axis=0)
        keep = sd > 1e-9
        A, B, names = A[:, keep], B[:, keep], [n for n, k in zip(names, keep, strict=True) if k]
        mu, sd = mu[keep], sd[keep]
        As, Bs = (A - mu) / sd, (B - mu) / sd
        target = np.log1p(y)
        y_mean = target.mean()
        lhs = As.T @ As + self.ridge * np.eye(As.shape[1])
        beta = np.linalg.solve(lhs, As.T @ (target - y_mean))
        resid = target - (y_mean + As @ beta)
        smear = float(np.mean(np.exp(resid)))
        pred = np.expm1(y_mean + Bs @ beta) * smear
        coefs = {n: round(float(b / s), 4) for n, b, s in zip(names, beta, sd, strict=True)}
        drivers = {k: v for k, v in coefs.items() if not k.startswith("m")}
        return ModelOutput(pred, {"ridge": self.ridge, "coefficients": drivers})


class _TreeModel(BaseModel):
    family = "Machine Learning"
    min_obs = 30
    uses_drivers = True

    def _estimator(self):  # pragma: no cover - abstract
        raise NotImplementedError

    def _features(self, X: pd.DataFrame, lag12: np.ndarray, ref: dict[str, float]) -> np.ndarray:
        m = X["month"].to_numpy(int)
        cols = [X["t"].to_numpy(float), np.sin(2 * np.pi * m / 12), np.cos(2 * np.pi * m / 12), np.log1p(lag12)]
        cols += list(_driver_block(X, ref).values())
        return np.column_stack(cols)

    def _forecast(self, y, h, X_train, X_future):
        if X_train is None or X_future is None:
            raise ValueError(f"{self.name} requires a calendar/driver design")
        n = len(y)
        ref = _refs(X_train)
        lag = np.r_[np.full(SEASON, np.nan), y[:-SEASON]]
        F = self._features(X_train, np.nan_to_num(lag), ref)[SEASON:]
        target = np.log1p(y[SEASON:])
        est = self._estimator().fit(F, target)
        ext = list(y)
        preds = []
        for k in range(h):  # recursive only beyond 12 steps (lag-12 is known before that)
            lag12 = np.array([ext[n + k - SEASON]])
            row = self._features(X_future.iloc[[k]], lag12, ref)
            p = float(np.expm1(est.predict(row)[0]))
            preds.append(p)
            ext.append(p)
        return ModelOutput(np.array(preds), {"n_train": len(target), "features": int(F.shape[1])})


class RandomForest(_TreeModel):
    name = "Random Forest"
    description = "Random forest on lag-12, calendar and driver features (log target)."

    def _estimator(self):
        from sklearn.ensemble import RandomForestRegressor

        return RandomForestRegressor(
            n_estimators=60, max_depth=6, min_samples_leaf=2, max_features=0.7, random_state=42, n_jobs=1
        )


class GradientBoosting(_TreeModel):
    name = "Gradient Boosting"
    description = "Gradient boosted trees (scikit-learn) on lag-12, calendar and driver features."

    def _estimator(self):
        from sklearn.ensemble import GradientBoostingRegressor

        return GradientBoostingRegressor(
            n_estimators=150, learning_rate=0.05, max_depth=2, subsample=0.8, random_state=42
        )


MODELS: list[BaseModel] = [
    Naive(),
    SeasonalNaive(),
    MovingAverage(),
    SES(),
    Holt(),
    HoltWinters(),
    ETS(),
    ARIMA(),
    SARIMA(),
    Croston(),
    SBA(),
    TSB(),
    Regression(),
    RandomForest(),
    GradientBoosting(),
]
MODEL_REGISTRY: dict[str, BaseModel] = {m.name: m for m in MODELS}


def model_catalog() -> list[dict[str, Any]]:
    return [
        {
            "name": m.name,
            "family": m.family,
            "description": m.description,
            "min_obs": m.min_obs,
            "uses_drivers": m.uses_drivers,
            "version": m.version,
        }
        for m in MODELS
    ]
