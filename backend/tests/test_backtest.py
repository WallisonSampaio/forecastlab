"""Rolling-origin backtest and data-leakage protection."""

import numpy as np
import pandas as pd

from app.backtesting import clean_stockouts, make_folds, run_backtest
from app.forecasting.models import BaseModel, ModelOutput, Naive


class SpyModel(BaseModel):
    """Records exactly what each fold receives."""

    name = "Spy"

    def __init__(self):
        self.calls = []

    def _forecast(self, y, h, X_train, X_future):
        self.calls.append({"y": y.copy(), "h": h, "X_train": X_train, "X_future": X_future})
        return ModelOutput(np.repeat(y.mean(), h))


def _design(n: int) -> pd.DataFrame:
    idx = pd.date_range("2021-01-01", periods=n, freq="MS")
    return pd.DataFrame(
        {
            "t": np.arange(n),
            "month": idx.month,
            "promotion": (np.arange(n) % 4 == 0).astype(float),
            "price": np.linspace(10, 12, n),
        },
        index=idx,
    )


def test_make_folds_expanding_window():
    folds = make_folds(60, n_folds=4, horizon=3)
    assert [f.train_end for f in folds] == [48, 51, 54, 57]
    assert folds[-1].test_idx == (57, 58, 59)
    for f in folds:
        assert max(range(f.train_end)) < min(f.test_idx)


def test_make_folds_respects_min_train():
    folds = make_folds(20, n_folds=4, horizon=3, min_train=12)
    assert all(f.train_end >= 12 for f in folds)
    assert [f.train_end for f in folds] == [14, 17]  # origins at 8 and 11 months are dropped


def test_no_future_data_reaches_training():
    y = np.arange(1, 61, dtype=float)
    spy = SpyModel()
    folds = make_folds(60, 4, 3)
    run_backtest(spy, y, _design(60), folds, clean=False)
    for call, fold in zip(spy.calls, folds, strict=True):
        assert len(call["y"]) == fold.train_end
        assert call["y"].max() == y[fold.train_end - 1]  # last training value, nothing after the origin
        assert call["X_train"].index.max() < call["X_future"].index.min()
        assert "units" not in call["X_future"].columns


def test_test_window_values_do_not_change_forecasts():
    rng = np.random.default_rng(1)
    y = rng.uniform(50, 150, 60)
    folds = make_folds(60, 4, 3)
    base = run_backtest(Naive(), y, _design(60), folds)
    perturbed = y.copy()
    perturbed[57:] = 10_000  # only the last test window changes
    out = run_backtest(Naive(), perturbed, _design(60), folds)
    np.testing.assert_allclose(base.forecast[:9], out.forecast[:9])  # earlier folds unaffected
    np.testing.assert_allclose(base.forecast[9:], out.forecast[9:])  # last fold forecast unaffected too


def test_future_drivers_are_frozen_not_actual():
    """Ex-ante evaluation: promotions/prices that happen in the test window are not revealed."""
    spy = SpyModel()
    X = _design(60)
    X.loc[X.index[57:], "promotion"] = 1.0
    X.loc[X.index[57:], "price"] = 99.0
    run_backtest(spy, np.ones(60), X, make_folds(60, 4, 3), clean=False)
    fut = spy.calls[-1]["X_future"]
    assert (fut["price"] < 99).all()
    assert (fut["promotion"] < 1).all()
    np.testing.assert_array_equal(fut["month"].to_numpy(), X["month"].to_numpy()[57:])


def test_stockout_cleaning_uses_training_data_only():
    y = np.array([100, 100, 100, 100, 20, 100], dtype=float)
    so = np.array([0, 0, 0, 0, 1, 0], dtype=float)
    cleaned = clean_stockouts(y[:5], so[:5])  # month 5 (index 5) is not visible
    assert cleaned[4] == 100
    assert np.array_equal(cleaned[:4], y[:4])


def test_backtest_output_shapes():
    y = np.linspace(100, 200, 60)
    bt = run_backtest(Naive(), y, _design(60), make_folds(60, 4, 3))
    assert len(bt.actual) == len(bt.forecast) == 12
    assert bt.fold == [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4]
    assert len(bt.fold_wmape) == 4
