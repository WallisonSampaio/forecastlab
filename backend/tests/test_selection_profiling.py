import numpy as np

from app.forecasting.profiling import profile_series
from app.forecasting.router import candidate_models
from app.model_selection import ModelEvaluation, model_confidence, rank_models, select_champion


def test_ranking_by_wmape_then_bias():
    evals = [
        ModelEvaluation("A", 0.10, 0.08, 10),
        ModelEvaluation("B", 0.10, 0.01, 12),
        ModelEvaluation("C", 0.20, 0.00, 5),
        ModelEvaluation("D", float("nan"), float("nan"), float("nan"), status="failed"),
    ]
    ranked = rank_models(evals)
    assert [e.model for e in ranked if e.rank] == ["B", "A", "C"]
    champion, challenger = select_champion(evals)
    assert champion.model == "B" and challenger.model == "A"
    assert ranked[-1].rank is None


def test_confidence_levels():
    good = ModelEvaluation("ETS", 0.08, 0.01, 1, fold_wmape=[0.07, 0.08, 0.09, 0.08])
    runner = ModelEvaluation("Naive", 0.20, 0.0, 1)
    assert model_confidence(good, runner, 60)[0] == "High"
    bad = ModelEvaluation("ETS", 0.55, 0.2, 1, fold_wmape=[0.2, 0.9, 0.4, 0.7])
    assert model_confidence(bad, ModelEvaluation("X", 0.56, 0, 1), 14)[0] == "Low"


def test_profile_detects_seasonal(seasonal_series):
    p = profile_series(seasonal_series)
    assert p["series_type"] == "Seasonal"
    assert p["seasonal_strength"] > 0.55


def test_profile_detects_intermittent():
    rng = np.random.default_rng(5)
    y = np.where(rng.random(48) < 0.3, rng.uniform(5, 20, 48), 0.0)
    p = profile_series(y)
    assert p["series_type"] == "Intermittent"
    assert p["adi"] >= 1.32


def test_profile_detects_trend_and_short_history():
    t = np.arange(48)
    rng = np.random.default_rng(2)
    p = profile_series(100 * 1.02**t * np.exp(rng.normal(0, 0.02, 48)))
    assert p["series_type"] == "Trending"
    assert profile_series(np.full(14, 50.0))["series_type"] == "Short History"


def test_profile_detects_structural_break():
    rng = np.random.default_rng(4)
    y = np.r_[np.full(30, 1000.0), np.full(30, 550.0)] * np.exp(rng.normal(0, 0.03, 60))
    assert profile_series(y)["series_type"] == "Structural Change"


def test_profile_detects_inactive():
    assert profile_series(np.r_[np.full(40, 30.0), np.zeros(8)])["series_type"] == "Inactive"


def test_router_routes_by_pattern():
    assert {"Croston", "SBA", "TSB"} <= set(candidate_models("Intermittent"))
    assert "SARIMA" in candidate_models("Seasonal") and "SARIMA" not in candidate_models("Intermittent")
    assert "Naive" in candidate_models("Stable", allowed=["ETS"])
    assert len(candidate_models("Stable", run_all=True)) == 15
