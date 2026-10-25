"""Rolling-origin cross validation (expanding window).

Example with 60 months, 4 folds, 3-month horizon::

    fold 1: train [0, 48)  -> test [48, 51)
    fold 2: train [0, 51)  -> test [51, 54)
    fold 3: train [0, 54)  -> test [54, 57)
    fold 4: train [0, 57)  -> test [57, 60)

Leakage protection: the model only ever receives ``y[:train_end]`` (a copy).
Drivers in the test window are *frozen* at their last known regular level
(ex-ante evaluation, see ``baseline_design``) - only the deterministic calendar
of the test window is used. Stock-out cleaning is applied inside each fold
using training data only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.forecasting.design import baseline_design
from app.forecasting.models import BaseModel

CALENDAR_COLUMNS = ("t", "month", "holiday")  # deterministic, known in advance


@dataclass(frozen=True)
class Fold:
    fold: int
    train_end: int  # exclusive
    test_idx: tuple[int, ...]

    @property
    def horizon(self) -> int:
        return len(self.test_idx)


def make_folds(
    n_obs: int, n_folds: int = 4, horizon: int = 3, step: int | None = None, min_train: int = 12
) -> list[Fold]:
    step = step or horizon
    folds: list[Fold] = []
    for k in range(n_folds):
        test_end = n_obs - (n_folds - 1 - k) * step
        train_end = test_end - horizon
        if train_end < min_train or test_end > n_obs:
            continue
        folds.append(Fold(len(folds) + 1, train_end, tuple(range(train_end, test_end))))
    return folds


def clean_stockouts(y: np.ndarray, stockout: np.ndarray | None) -> np.ndarray:
    """Replace stock-out-depressed sales by the mean of nearby clean months.

    Uses only the values present in ``y`` - callers pass training data only.
    """
    y = np.asarray(y, dtype=float).copy()
    if stockout is None:
        return y
    so = np.asarray(stockout, dtype=float)[: len(y)]
    for i in map(int, np.flatnonzero(so > 0)):
        neigh = [y[j] for j in range(max(0, i - 2), min(len(y), i + 3)) if j != i and so[j] == 0]
        if neigh:
            y[i] = max(y[i], float(np.mean(neigh)))
    return y


@dataclass
class BacktestOutput:
    fold: list[int]
    index: list[int]
    step: list[int]
    actual: np.ndarray
    forecast: np.ndarray
    fold_wmape: list[float]
    params: dict = field(default_factory=dict)  # parameters fitted on the last fold


def run_backtest(
    model: BaseModel,
    y: np.ndarray,
    X: pd.DataFrame | None,
    folds: list[Fold],
    stockout: np.ndarray | None = None,
    clean: bool = True,
) -> BacktestOutput:
    y = np.asarray(y, dtype=float)
    folds_out, idx_out, step_out = [], [], []
    act, fc, fold_w = [], [], []
    params: dict = {}
    for f in folds:
        train_end = f.train_end
        y_train = y[:train_end].copy()
        if clean:
            y_train = clean_stockouts(y_train, None if stockout is None else stockout[:train_end])
        X_train = X.iloc[:train_end].copy() if X is not None else None
        X_test = None
        if X is not None and X_train is not None:
            calendar = X.iloc[list(f.test_idx)][[c for c in CALENDAR_COLUMNS if c in X.columns]]
            X_test = baseline_design(X_train, calendar)
        out = model.forecast(y_train, f.horizon, X_train, X_test)
        pred, params = out.mean, out.params
        a = y[list(f.test_idx)]
        folds_out += [f.fold] * f.horizon
        idx_out += list(f.test_idx)
        step_out += list(range(1, f.horizon + 1))
        act.append(a)
        fc.append(pred)
        denom = np.abs(a).sum()
        fold_w.append(float(np.abs(pred - a).sum() / denom) if denom > 0 else 0.0)
    return BacktestOutput(
        fold=folds_out,
        index=idx_out,
        step=step_out,
        actual=np.concatenate(act) if act else np.array([]),
        forecast=np.concatenate(fc) if fc else np.array([]),
        fold_wmape=fold_w,
        params=params,
    )
