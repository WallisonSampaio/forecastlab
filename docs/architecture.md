# Architecture

> ForecastLab · Developed by Wallison Sampaio — Commercial Intelligence | Supply Chain | Data & AI Analytics Specialist ·
> [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

ForecastLab is a **local, modular, decoupled full-stack application**. Each layer can be replaced independently when
the product moves to an enterprise environment (see [enterprise_readiness.md](enterprise_readiness.md)).

```text
                         FORECASTLAB
             AI Demand Planning & S&OP Platform

                         FRONTEND
          React 19 + TypeScript + Vite + Tailwind + ECharts
                         │  REST (/api, JSON)
                         ↓
                       FastAPI
                         │
        ┌────────────────┼──────────────────┐
        ↓                ↓                  ↓
     DuckDB        Forecast Engine    Scenario / S&OP / FVA
        │          (Python models)          Engines
        └────────────┬───┴──────────────────┘
                     ↓
               Semantic Layer
                     ↓
          AI Demand Analyst  ──►  Ollama (local LLM)
```

## Backend modules (`backend/app`)

| Module | Responsibility |
|---|---|
| `api/` | FastAPI routers: `data`, `forecast` (runs, workspace, hierarchy, models, overrides), `planning` (scenarios, S&OP, FVA, alerts, AI, semantic), `export` |
| `ingestion/` | File readers (xlsx/csv/parquet), canonical schema, EN/PT column aliases, Excel template |
| `validation/` | Dataset Health Check, Data Quality Score, critical-error blocking, monthly aggregation |
| `forecasting/` | Model zoo (15 models), series profiling & classification, Model Candidate Router, panel builder, per-series worker, parallel engine |
| `backtesting/` | Rolling-origin folds, ex-ante driver freezing, stock-out cleaning |
| `metrics/` | MAE, RMSE, MAPE, sMAPE, WMAPE, MASE, Bias, accuracy, bias class |
| `model_selection/` | Ranking, Champion/Challenger, model confidence |
| `reconciliation/` | Bottom-up and top-down reconcilers (strategy interface; MinT stub) |
| `scenarios/` | Elasticity estimation, What-If engine, scenario store & presets |
| `sop/` | Executive cockpit, Target Feasibility Engine, goal allocation |
| `fva/` | Forecast Value Added (naive → statistical → consensus) |
| `alerts/` | Alert Center rules with explanations |
| `semantic_layer/` | Governed metric & dimension catalog + query executor |
| `ai/` | Intent parser, handlers, deterministic NLG, Ollama client, grounding guard |
| `exports/` | Excel workbooks and HTML executive report |
| `services/` | Dataset lifecycle, run jobs, planning context (joined & cached view) |

## Request flow

1. The frontend calls `/api/...` (Vite proxy in development, nginx in Docker).
2. Read endpoints build (or reuse) a cached **PlanningContext** — actuals, champion & challenger forecasts,
   overrides → consensus, plan, backtests — for the *active dataset* and *active run*.
3. Writes (upload, overrides, scenarios, runs) invalidate the context cache.
4. Forecast runs execute in a background thread; series are processed in a **process pool** (one BLAS thread per
   worker) and results are persisted to DuckDB (model registry, backtests, forecasts, profiles, run registry).

## Frontend (`frontend/src`)

| Folder | Content |
|---|---|
| `pages/` | Home (landing/demo), Overview, Data, Forecasting (workspace + hierarchy), ModelPerformance, Scenarios, SOP, FVA, AIAnalyst, Alerts, Settings |
| `components/` | Layout (sidebar, top bar, signature), FilterBar, DataTable, RunControls, UI kit |
| `charts/` | ECharts wrapper, TimelineChart (Actual/Base/Consensus/Budget/Target/P10–P90), bar/line/waterfall/heatmap, ChartRenderer for AI specs |
| `hooks/` | React Query helpers, job polling, global filters (Zustand), debounce |
| `services/` | REST client |
| `types/` | API contracts |

### Visual system

* Brand chrome: yellow + blue theme — navy sidebar (`#2D3277`) with a yellow active state (`#FFE600`), yellow top
  bar (`#FFF159`), action blue (`#3483FA`) for buttons and links, light gray page plane (`#EDEDED`). The ForecastLab
  mark is the project's own logo.
* Chart colors use the first five slots of a validated categorical palette (adjacent CVD ΔE ≥ 8 in light and dark):
  Statistical = blue, Budget = orange, Consensus = aqua, Target = yellow, Challenger = magenta, Actual = ink.
  Low-contrast slots are always paired with a legend, dash patterns and a table view.
* Status colors (good / warning / critical) are reserved for classifications and always carry an icon + label.
* Sequential blue ramp for WMAPE heatmaps; diverging blue ↔ red with a neutral midpoint for bias.

## Runtime topology

| Mode | Components |
|---|---|
| Local dev | `uvicorn` on :8000, Vite dev server on :3000 (proxy `/api`), optional Ollama on :11434 |
| Docker | `frontend` (nginx :3000 → `/api` → backend), `backend` (:8000, DuckDB on a named volume), `ollama`, `ollama-pull` |

## Design decisions

* **DuckDB** — zero-infrastructure analytical store; SQL kept portable to PostgreSQL / Azure SQL.
* **Ex-ante backtests** — future drivers are never revealed to the models, so accuracy is honest.
* **Engines compute, AI explains** — the LLM is an explanation layer behind a numeric grounding check.
* **Bottom-up reconciliation** — coherent numbers at every hierarchy level by construction.
