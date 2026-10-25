# Scenario planning & What-If engine

> ForecastLab · Developed by Wallison Sampaio · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

## Scenarios

| Scenario | Definition |
|---|---|
| **Base** | Statistical forecast + approved commercial overrides (consensus). Read-only reference. |
| **Conservative** | Price +2% (pass-through), distribution −3%, marketing −10%, customer growth −2%, market −1.5%. |
| **Aggressive** | Price −2%, distribution +6%, promotions in the 2 peak months, merchandising in the peak month, marketing +15%, customer growth +2%, market +1%. |
| **Custom** | Any combination saved by the user (create, duplicate, edit, compare, delete). |

## Levers

price · distribution · promotion (months + discount) · merchandising (months) · marketing · customer growth ·
market growth · scope (region / channel / category / customer) · start from consensus or statistical forecast.

## Model

```text
units   = start × (1 + Δprice)^ε_price
                × (min(100, D₀(1 + Δdist)) / D₀)^ε_dist
                × (1 + promo_uplift)           in promoted months
                × (1 + merch_uplift)           in merchandising months
                × (1 + Δmarketing)^ε_mkt
                × (1 + customer growth) × (1 + market growth)
revenue = units × price × (1 + Δprice) × (1 − promo discount in promoted months)
```

Impact by lever uses exact log-share attribution of the multiplicative change.

## Elasticities (estimated from history)

Per category, a pooled **within-series** log-log regression (series fixed effects) of demand on regular price,
numeric distribution, promotion, merchandising, marketing, month effects and trend:

* Promo months use the last **regular** (shelf) price so the discount is not confused with the promo effect.
* **Cluster-robust** standard errors by series (months of the same series are correlated).
* **Empirical-Bayes shrinkage** towards industry priors, weighted by precision — weakly identified coefficients
  (e.g. list-price changes that coincide with competitor events) are pulled towards the prior.
* Results are clipped to plausible ranges; the Scenarios page shows the estimate next to the synthetic ground truth.

## Comparator

Units, revenue, vs Base, vs Budget, vs Target for every scenario plus monthly revenue lines against budget and target.
