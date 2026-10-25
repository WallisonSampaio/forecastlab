# LinkedIn portfolio kit

> ForecastLab · Developed by Wallison Sampaio — Commercial Intelligence | Supply Chain | Data & AI Analytics Specialist ·
> [www.linkedin.com/in/wallisonsampaio](https://www.linkedin.com/in/wallisonsampaio)

## Headline

> **I built ForecastLab — a full-stack AI-powered Demand Planning & S&OP platform that backtests multiple forecasting
> models, selects the best model per SKU/customer, simulates commercial scenarios and evaluates whether business
> targets are statistically realistic.**

## Post draft (EN)

I built **ForecastLab**, an AI Demand Planning & S&OP decision platform — 100% local, zero paid APIs.

🔹 15 forecasting models compete per Customer × SKU in a rolling-origin backtest (no data leakage)
🔹 Champion & Challenger, model confidence, P10/P50/P90 forecasts
🔹 Commercial overrides → consensus, and FVA to prove whether overrides add value
🔹 What-if scenarios with elasticities estimated from history
🔹 "Is this target realistic?" — probability, P90 check, required growth and the lever that would close the gap
🔹 A local AI analyst (Ollama) that explains results — and is not allowed to invent numbers

Stack: React + TypeScript · FastAPI · DuckDB · statsmodels / scikit-learn · ECharts · Docker.
All data is synthetic. Code on GitHub 👇

## Post draft (PT-BR)

Construí o **ForecastLab**, uma plataforma de Demand Planning e S&OP com IA — 100% local, sem APIs pagas.
15 modelos competem por cliente × SKU em backtesting rolling-origin; Champion/Challenger; previsão P10/P50/P90;
ajustes comerciais → consensus com FVA; cenários what-if com elasticidades estimadas; motor de viabilidade de metas;
e um analista de IA local que explica os resultados sem inventar números. Dados 100% sintéticos.

## Screenshots

| File | Screen |
|---|---|
| `screenshots/sop-cockpit.png` | **Hero** — S&OP Executive Cockpit |
| `screenshots/forecast-workspace.png` | Forecast + confidence interval |
| `screenshots/model-performance.png` | Champion vs Challenger / leaderboard |
| `screenshots/scenarios.png` | Base vs Aggressive |
| `screenshots/ai-analyst.png` | AI Analyst explaining an aggressive target |
| `screenshots/data-health.png` | Data Quality Check |

## Video storyboard (60–120 s)

| Scene | Screen | Narration cue |
|---|---|---|
| 1 | Home | "ForecastLab — AI Demand Planning & S&OP." |
| 2 | Data → upload `forecastlab_sample_upload.xlsx` | "Upload an Excel history…" |
| 3 | Health check & quality score | "…validated: quality score, critical errors block the forecast." |
| 4 | Run forecast (progress) | "15 models, rolling-origin backtest." |
| 5 | Workspace → champion | "Best model per series, with confidence." |
| 6 | Forecast chart with P10–P90 | "12-month probabilistic forecast." |
| 7 | Add a promotion override | "Commercial event → consensus." |
| 8 | Scenarios → Aggressive | "Scenario recalculated with estimated elasticities." |
| 9 | S&OP → target feasibility | "Is the target realistic? Probability and gap." |
| 10 | AI Analyst → "Is December target realistic?" | "The AI explains the risk — numbers from the engines." |
| End | Signature card | **ForecastLab — Developed by Wallison Sampaio** |
