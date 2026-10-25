import numpy as np
import pandas as pd
import pytest

from app.forecasting.models import MODEL_REGISTRY, MODELS, TSB, Croston, SeasonalNaive


def _design(n: int, start: str = "2021-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="MS")
    return pd.DataFrame(
        {
            "t": np.arange(n),
            "month": idx.month,
            "promotion": (np.arange(n) % 5 == 0).astype(float),
            "price": 10.0,
            "distribution": 70.0,
        },
        index=idx,
    )


def test_at_least_eight_models():
    assert len(MODELS) >= 8
    families = {m.family for m in MODELS}
    assert {"Baseline", "Exponential Smoothing", "ARIMA", "Intermittent", "Regression", "Machine Learning"} <= families


@pytest.mark.parametrize("name", list(MODEL_REGISTRY))
def test_every_model_forecasts_h_non_negative_values(name, seasonal_series):
    model = MODEL_REGISTRY[name]
    X = _design(72)
    out = model.forecast(seasonal_series[:48], 6, X.iloc[:48], X.iloc[48:54])
    assert out.mean.shape == (6,)
    assert np.isfinite(out.mean).all()
    assert (out.mean >= 0).all()


def test_seasonal_naive_repeats_last_year(seasonal_series):
    out = SeasonalNaive().forecast(seasonal_series, 12)
    np.testing.assert_allclose(out.mean, seasonal_series[-12:])


def test_croston_and_tsb_on_intermittent_demand():
    y = np.array([0, 0, 10, 0, 0, 0, 12, 0, 0, 8, 0, 0, 0, 0, 11, 0, 0, 9], dtype=float)
    c = Croston().forecast(y, 3).mean
    assert np.allclose(c, c[0]) and 1.5 < c[0] < 6
    t = TSB().forecast(np.r_[y, np.zeros(12)], 3).mean  # obsolescence: TSB decays towards 0
    assert t[0] < TSB().forecast(y, 3).mean[0]


def test_regression_reacts_to_promotion_driver():
    rng = np.random.default_rng(3)
    X = _design(60)
    y = 100 * (1 + 0.5 * X["promotion"].to_numpy()) * np.exp(rng.normal(0, 0.03, 60))
    fut_on, fut_off = X.iloc[48:50].copy(), X.iloc[48:50].copy()
    fut_on["promotion"], fut_off["promotion"] = 1.0, 0.0
    m = MODEL_REGISTRY["Regression"]
    on = m.forecast(y[:48], 2, X.iloc[:48], fut_on).mean
    off = m.forecast(y[:48], 2, X.iloc[:48], fut_off).mean
    assert (on / off).mean() == pytest.approx(1.5, rel=0.12)


def test_target_in_future_design_is_rejected(seasonal_series):
    X = _design(60)
    fut = X.iloc[48:50].assign(units=1.0)
    with pytest.raises(ValueError):
        MODEL_REGISTRY["Naive"].forecast(seasonal_series[:48], 2, X.iloc[:48], fut)
