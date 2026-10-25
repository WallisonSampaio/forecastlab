# REST API

> ForecastLab · Developed by Wallison Sampaio · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

Interactive OpenAPI docs: **http://localhost:8000/docs**.

Hierarchy filters are query parameters accepted by most read endpoints: `region`, `channel`, `customer`,
`category`, `brand`, `sku` (repeatable). `measure` = `units` | `revenue`.

## System
| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | status, active dataset, running job |
| GET | `/api/meta` | app info, author/branding, model catalog, horizons, AI status |

## Data
| Method | Path | Description |
|---|---|---|
| POST | `/api/data/upload` | multipart file (`.xlsx/.csv/.parquet`) → validation report; accepted files become a new dataset version and start a run (`run_forecast=true`) |
| POST | `/api/data/demo` | `{seed, run_forecast}` — generate & activate the synthetic dataset |
| GET | `/api/data/datasets` | dataset versions |
| GET | `/api/data/active` | active dataset + health report |
| POST | `/api/data/datasets/{version}/activate` | switch dataset |
| GET | `/api/data/template` | Excel template |
| GET | `/api/data/preview` | rows (limit/offset/filters) |
| GET | `/api/data/dimensions` | hierarchy members, series list, horizon |
| GET | `/api/data/eda` | trend, seasonality, volatility, promo & distribution effects |
| GET | `/api/data/profiles` | series profiling & classification |

## Forecasting
| Method | Path | Description |
|---|---|---|
| POST | `/api/forecast/run` | `{horizon, n_folds, fold_horizon, clean_stockouts, run_all_models, models}` |
| GET | `/api/forecast/job` | running job progress (or `null`) |
| GET | `/api/forecast/runs` · `/api/forecast/runs/{id}` | Forecast Run Registry |
| POST | `/api/forecast/runs/{id}/activate` | use a previous run |
| GET | `/api/forecast/models` | model catalog |
| GET | `/api/forecast/series` | series with champion, WMAPE, bias, LTM, 12M forecast |
| GET | `/api/forecast/series-detail?series_id=` | workspace payload: header, selection, next month & interval, timeline, leaderboard, backtest, overrides |
| GET | `/api/forecast/aggregate` | aggregated timeline & KPIs for any hierarchy node |
| GET | `/api/forecast/hierarchy?level=&method=` | drill-down table (bottom-up / top-down) |

## Models
`GET /api/models/leaderboard`, `/api/models/distribution`, `/api/models/heatmap?metric=wmape|bias`,
`/api/models/performance`, `/api/models/registry?series_id=`.

## Overrides
`GET /api/overrides`, `GET /api/overrides/event-library`, `POST /api/overrides`
(`{customer?, sku?, date, event_type, uplift_pct, comment, created_by}`), `PUT/DELETE /api/overrides/{id}`.

## Scenarios
`GET/POST /api/scenarios`, `PUT/DELETE /api/scenarios/{id}`, `POST /api/scenarios/{id}/duplicate`,
`POST /api/scenarios/simulate` (`{params, filters}`), `GET /api/scenarios/compare?ids=&measure=`,
`GET /api/scenarios/elasticities`.

Scenario params: `price_change_pct, distribution_change_pct, promo_months[], promo_discount_pct, merch_months[],
marketing_change_pct, customer_growth_pct, market_growth_pct, scope{}, base (consensus|statistical)`.

## S&OP, FVA, alerts
`GET /api/overview`, `GET /api/sop/cockpit`, `GET /api/sop/feasibility?months=`,
`POST /api/sop/allocation` (`{dimension, method, total_target?, weights?, filters, measure}`),
`GET /api/fva`, `GET /api/alerts?severity=&type=`.

## AI & semantic layer
| Method | Path | Description |
|---|---|---|
| POST | `/api/ai/ask` | `{question, filters, use_llm}` → `{answer, insights, metrics, chart, table, recommendations, filters, meta}` |
| GET | `/api/ai/status` | Ollama reachability & model |
| GET | `/api/ai/suggestions?lang=en|pt` | example questions |
| GET | `/api/semantic/catalog` | governed metrics & dimensions |

## Exports
`GET /api/export/excel?scenario_id=` (planning workbook), `GET /api/export/executive-excel`,
`GET /api/export/executive-html[?download=true]`.
