import math

import pytest

from app.metrics import bias, bias_class, forecast_accuracy, mae, mape, mase, rmse, smape, wmape


def test_mae_rmse():
    a, f = [100, 200, 300], [110, 190, 330]
    assert mae(a, f) == pytest.approx((10 + 10 + 30) / 3)
    assert rmse(a, f) == pytest.approx(math.sqrt((100 + 100 + 900) / 3))


def test_wmape_is_weighted_by_volume():
    a, f = [100, 900], [150, 900]
    assert wmape(a, f) == pytest.approx(50 / 1000)
    # MAPE weights both periods equally -> much larger than WMAPE here.
    assert mape(a, f) == pytest.approx(0.25)


def test_mape_ignores_zero_actuals():
    assert mape([0, 100], [10, 110]) == pytest.approx(0.10)
    assert math.isnan(mape([0, 0], [1, 1]))


def test_smape_bounds_and_zero_zero():
    assert smape([0, 0], [0, 0]) == 0.0
    assert smape([100], [0]) == pytest.approx(2.0)


def test_bias_sign_convention():
    assert bias([100, 100], [120, 100]) == pytest.approx(0.10)  # over-forecast is positive
    assert bias([100, 100], [80, 100]) == pytest.approx(-0.10)


def test_bias_class_thresholds():
    assert bias_class(0.08) == "Over"
    assert bias_class(-0.08) == "Under"
    assert bias_class(0.03) == "Balanced"


def test_forecast_accuracy_floor():
    assert forecast_accuracy(0.084) == pytest.approx(0.916)
    assert forecast_accuracy(1.4) == 0.0


def test_mase_against_seasonal_naive():
    insample = list(range(1, 25))  # seasonal naive error = 12 every period
    assert mase([30], [36], insample, m=12) == pytest.approx(0.5)


def test_wmape_all_zero_actuals():
    assert wmape([0, 0], [0, 0]) == 0.0
    assert math.isnan(wmape([0, 0], [1, 0]))
