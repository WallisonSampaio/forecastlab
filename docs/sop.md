# S&OP, target intelligence and FVA

> ForecastLab · Developed by Wallison Sampaio · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

## Executive cockpit

Actual (LTM) · Statistical forecast · Consensus forecast · Budget · Sales target · Gap vs budget (absolute and %) ·
Gap vs target · **Risk** (Σ series where consensus < budget) · **Opportunity** (Σ series where consensus > budget) ·
quarterly view · top risks / opportunities · feasibility by region and channel. Units or revenue, any hierarchy
filter.

## Baseline vs incremental

```text
Baseline demand (statistical P50)
+ Incremental demand (commercial overrides: Σ uplift % × baseline)
= Consensus forecast
```

Event library: Promotion, Merchandising, Distribution Gain/Loss, New Store, Customer Gain/Loss, Campaign,
Price Change, New Product, Delisting, Competitor Action. An override can target a SKU at a customer, all SKUs of a
customer, or any month in the horizon.

## Target Feasibility Engine — "Is this target realistic?"

The consensus is treated as N(consensus, σ) with σ aggregated from out-of-sample backtest errors.

| Input | Use |
|---|---|
| P(demand ≥ target) | primary classification |
| target vs P10 / P50 / P90 | position in the plausible range |
| required growth vs last year vs historical growth | ambition check |
| customer potential | target above addressable potential → Aggressive |
| planned events | incremental already in the consensus |
| historical volatility | context |

| Class | Rule |
|---|---|
| 🔵 UNDERESTIMATED | target ≤ P10 or probability ≥ 90% |
| 🟢 REALISTIC | probability ≥ 50% |
| 🟡 STRETCH | 20% ≤ probability < 50% and target ≤ P90 |
| 🔴 AGGRESSIVE | otherwise, or above potential, or required growth far above history |

**Calibration** — required incremental growth vs budget (e.g. budget R$10M, target R$11M → +10%), gap vs consensus,
and the single lever change that would close the gap (distribution, price, marketing or promoted months), flagged
plausible / unrealistic.

## Goal allocation

Distribute a total target by region, channel, customer, category or SKU:

* **Historical weight** — share of the last 12 months
* **Potential based** — share of growth headroom (customer potential − current volume)
* **Forecast based** — share of the consensus forecast
* **Strategic** — user weights (editable grid)

Each allocated target gets its own feasibility class and probability.

## Forecast Value Added

Cell by cell (Customer × SKU × Month) over the last 12 months:

```text
Naive  →  Statistical (champion, out-of-sample)  →  Consensus (after planner overrides)
FVA = error(previous step) − error(this step)
```

Example: statistical 100, planner override 120, actual 103 → **"Override reduced forecast accuracy."**

The FVA page shows the stairstep, monthly WMAPE by step, % of overrides adding value, FVA by event type, planner,
direction and magnitude, the best/worst override and the full override log.

## Alert Center

🔴 High Forecast Error · 🔴 Severe Overforecast · 🔵 Severe Underforecast · 🟠 Target Above P90 ·
🟠 Forecast Structural Change (tracking signal) · 🟡 Challenger Model Improving · 🟢 Commercial Opportunity — each
with issue, affected entity, magnitude, potential impact, explanation and recommended investigation.
