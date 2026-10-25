# Forecasting methodology

> ForecastLab · Developed by Wallison Sampaio · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

## 1. Panel construction

* Granularity: **Customer × SKU × Month** (daily/weekly uploads are aggregated monthly).
* Each series runs from its first record to the dataset end; missing months are zero demand.
* Calendar design per month: time index `t`, `month`, Brazilian holidays (Carnaval and Easter computed per year).
* Drivers when available: promotion, price, distribution, merchandising, marketing investment.

## 2. Series profiling & classification

| Statistic | Definition |
|---|---|
| mean, median, variance, CV | descriptive statistics |
| zero-demand % | share of months with zero demand |
| ADI / CV² | average demand interval and squared CV of non-zero demand (Syntetos–Boylan) |
| trend strength | `max(0, 1 − Var(R)/Var(T+R))` from robust STL |
| seasonal strength | `max(0, 1 − Var(R)/Var(S+R))` from robust STL |
| structural break | best single change-point (two-segment mean) vs. linear trend SSE |
| promo lift / correlation | demand vs. rolling median in promo vs. non-promo months |
| distribution correlation | deseasonalised demand vs. numeric distribution |

Classification order (first match wins): Inactive → Short History → Intermittent → Distribution Driven →
Structural Change → Seasonal → Promo Driven → Trending / Declining → Volatile → Stable. Each series stores the
human-readable reason (e.g. *"ADI 2.10 ≥ 1.32 (52% zero months)"*).

## 3. Model zoo (15 models)

| Family | Models |
|---|---|
| Baselines | Naive, Seasonal Naive, Moving Average (3) |
| Exponential smoothing | SES, Holt (damped), Holt-Winters (damped, add/mul seasonality), ETS (automatic by AICc) |
| ARIMA | ARIMA(1,1,1) with drift when significant, SARIMA(0,1,1)(0,1,1)₁₂ on log scale |
| Intermittent | Croston, SBA (bias-corrected), TSB (handles obsolescence) |
| Regression | Ridge on log demand: trend, monthly seasonality, promotion, log price, log distribution, merchandising, log marketing, holidays (smearing back-transform) |
| Machine learning | Random Forest, Gradient Boosting (scikit-learn) on lag-12, calendar and drivers (recursive beyond 12 steps) |

All models share one stateless interface: `forecast(y_train, h, X_train, X_future) → mean, params`.

## 4. Model Candidate Router

| Series type | Candidates (Naive always included) |
|---|---|
| Intermittent | Croston, SBA, TSB, Moving Average |
| Seasonal | Seasonal Naive, Holt-Winters, ETS, SARIMA, Regression |
| Trending / Declining | Holt, ETS, ARIMA, Regression, Seasonal Naive |
| Promo Driven | Regression, Random Forest, Gradient Boosting, ETS, Seasonal Naive |
| Distribution Driven | Regression, Gradient Boosting, Holt, ETS |
| Structural Change | SES, Holt, ETS, ARIMA, Moving Average |
| Volatile | Moving Average, SES, ETS, Random Forest, Gradient Boosting, Seasonal Naive |
| Stable | SES, Moving Average, ETS, ARIMA, Regression, Seasonal Naive |
| Short History | Moving Average, SES, Holt, ETS |

The router can be disabled per run ("run all 15 models").

## 5. Rolling-origin backtest

* Expanding window; default **4 folds × 3 months** → the last 12 months are forecast out-of-sample.
* Folds with fewer than 12 training months are skipped; models needing more history are marked
  `insufficient_history`.
* **No leakage**: training data is `y[:origin]` only; drivers in the test window are frozen at business-as-usual
  values computed from the training window (regular price, last distribution, median marketing, usual promo
  intensity); stock-out cleaning only uses training months. Tests: `backend/tests/test_backtest.py`.

## 6. Metrics

| Metric | Formula |
|---|---|
| MAE | mean(|F − A|) |
| RMSE | √mean((F − A)²) |
| MAPE | mean(|F − A| / A), A ≠ 0 |
| sMAPE | mean(2|F − A| / (|A| + |F|)) |
| **WMAPE** (primary) | Σ|F − A| / Σ|A| |
| MASE | MAE / in-sample seasonal-naive MAE |
| Bias | Σ(F − A) / ΣA (positive = over-forecast) |
| Forecast Accuracy | max(0, 1 − WMAPE) |

Bias classes: 🔵 Under (< −5%) · 🟢 Balanced · 🔴 Over (> +5%).

## 7. Champion, Challenger & confidence

Ranking: WMAPE → |Bias| → RMSE. Rank 1 = **Champion**, rank 2 = **Challenger**.

Confidence score (0–100): error (≤15% → 40 pts), fold stability (σ of fold WMAPE), history depth (≥48 months),
champion margin over the challenger. ≥75 High · ≥50 Medium · otherwise Low.

## 8. Forecast & prediction intervals

* Final fit on the full (stock-out cleaned) history; default horizon 12 months (3/6/12/18/24 available).
* σ₁ = RMSE of the champion's out-of-sample backtest errors; σₕ = σ₁·√(h / h̄).
* P50 = model forecast; P10/P90 = P50 ∓ 1.2816·σₕ (P10 floored at 0).
* Aggregation across series/months: `σ = √((1−ρ)Σσᵢ² + ρ(Σσᵢ)²)` with ρ = 0.3.

## 9. Hierarchy & reconciliation

Company → Region → Channel → Customer → Category → SKU. Bottom-up by default (every level is the exact sum of its
Customer × SKU forecasts); top-down by historical proportions is available in the Hierarchy explorer; MinT /
middle-out are defined in the reconciler interface for a future release.

## 10. Registries & versioning

* **Model registry**: SeriesID, Model, ModelVersion, TrainingDate, data cutoff, WMAPE, Bias, MAE, RMSE, MASE,
  fold WMAPEs, rank, Parameters (JSON), Champion/Challenger flags.
* **Forecast run registry**: RunID, timestamp, DatasetVersion, horizon, engine version, scenario, status,
  duration, series and models evaluated, run parameters and summary.
* **Dataset versioning**: every upload → `dataset_YYYY_MM_vNN`.

## Performance

220 series × ~6 routed models × 5 fits ≈ 6,600 model fits per run, processed in parallel worker processes
(≈2–5 minutes on a laptop). Disable the router only for demonstrations.
