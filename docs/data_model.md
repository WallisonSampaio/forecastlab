# Data model

> ForecastLab · Developed by Wallison Sampaio · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

## Upload format

Minimum columns: `Date, Region, Channel, Customer, SKU, Units`.
Optional: `CustomerLocation, CustomerPotential, Product, Category, Brand, Revenue, Price, Promotion, Distribution,
StockOut, Holiday, MarketingInvestment, MerchandisingEvent`.

* Column names are matched case/accent-insensitively with EN/PT aliases (e.g. `Data`, `Região`, `Cliente`,
  `Quantidade`, `Preço`, `Promoção`).
* Any day of the month is accepted; rows are aggregated to **Customer × SKU × Month**.
* An Excel sheet named `Plan…` with `Date, Customer, SKU, BudgetUnits, TargetUnits[, BudgetRevenue, TargetRevenue]`
  is used as the plan; otherwise budget = same month last year × 1.05 and target = budget × 1.05.
* Download the template from **Data → Download template** (`/api/data/template`).

## Validation rules

| Severity | Checks |
|---|---|
| Critical (blocks the forecast) | missing required columns, empty file, invalid dates, missing Date/Customer/SKU/Region/Channel, negative or non-numeric units, < 6 months of history |
| Warning | duplicated rows, future dates, missing units (≤ 20%), negative revenue/price/marketing, distribution outside 0–100, outliers (robust z > 3.5), short series (< 12 months) |
| Info | rows aggregated to monthly, zero-demand periods, optional columns missing |

**Data Quality Score** = 35% Completeness + 30% Consistency + 20% Historical Depth (median months / 48) +
15% Granularity (hierarchy attributes present).

## DuckDB tables

| Table | Grain | Key columns |
|---|---|---|
| `datasets` | dataset version | `dataset_version`, name, source, rows, series, period, quality score, status, active flag, validation JSON |
| `sales` | version × date × customer × sku | all canonical fields |
| `plan` | version × date × customer × sku | budget/target units & revenue |
| `historical_overrides` | version × date × customer × sku | planner, event type, adjustment %, comment |
| `overrides` | override | customer (nullable = all), sku (nullable = all), month, event type, uplift %, comment, author |
| `forecast_runs` | run | run id, timestamps, dataset version, horizon, engine version, scenario, status, duration, params, summary |
| `series_selection` | run × series | series type, champion, challenger, WMAPE, bias, confidence |
| `series_profiles` | run × series | profiling statistics and classification reason |
| `model_registry` | run × series × model | model version, training date, metrics, rank, parameters, champion/challenger flags |
| `backtest_results` | run × series × model × month | fold, origin, horizon step, actual, forecast |
| `forecasts` | run × series × month × role | champion/challenger P50, σ, P10, P90 |
| `scenarios` | scenario | name, kind, description, parameters JSON |
| `app_state` | key | active dataset, active run |

Series id = `"{Customer}|{SKU}"`.

## Synthetic generator

`python -m synthetic_data_generator --seed 42` writes `data/synthetic/`:

| File | Content |
|---|---|
| `sales_history.csv/.parquet` | 60 months × 220 series, every PRD field |
| `budget_target_plan.csv` | budget & target, last 12 history months + 12 future months |
| `historical_overrides.csv` | planner adjustments (informed and optimistic) for FVA |
| `pending_commercial_events.csv` | future commercial events seeded into the consensus |
| `metadata.json` | seed, patterns per SKU, true elasticities, events (ground truth for validation) |

Demand = level × trend × seasonality × calendar events × store openings × distribution^0.9 × relative price^ε ×
promotion × merchandising × marketing^0.07 × structural breaks × noise × (1 − stock-out loss).
