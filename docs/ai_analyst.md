# AI Demand Analyst

> ForecastLab · Developed by Wallison Sampaio · [LinkedIn](https://www.linkedin.com/in/wallisonsampaio)

## Fundamental rule

**The LLM cannot invent metrics.** Numbers are produced by the forecasting, scenario, S&OP and FVA engines; the
LLM only interprets, compares, explains, summarises and recommends.

```text
User Question
      ↓
Intent Extraction        bilingual rules (EN / PT-BR) → LLM classifier fallback
      ↓
Semantic Query           governed metric × dimension × filters × period
      ↓
DuckDB / Engines         forecast · scenario · feasibility · FVA · alerts
      ↓
Structured Result        facts + KPI cards + chart spec + table
      ↓
LLM Explanation          Ollama, JSON schema output, temperature 0.1
      ↓
Grounding Guard          every number in the text must exist in the facts
      ↓
Answer                   {answer, insights, metrics, chart, recommendations, filters} + meta
```

## Intents

| Intent | Example | Engine |
|---|---|---|
| `forecast_drivers` | *What is driving forecast growth in July?* | LY → statistical by category → events → consensus bridge (waterfall) |
| `worst_accuracy` | *Which SKUs have the worst forecast accuracy?* | semantic query `wmape BY sku` |
| `bias_ranking` | *Which customers are overforecasted?* | semantic query `bias BY customer` |
| `target_feasibility` | *Is December target realistic?* | Target Feasibility Engine |
| `best_model` | *Which model performs best for SKU X?* | leaderboard for the selection |
| `what_if` | *What happens if distribution increases by 10%?* | Scenario engine with estimated elasticities |
| `fva_overrides` | *Which commercial overrides reduced accuracy?* | FVA report |
| `budget_gap` | *Where are we below budget?* | semantic query `gap_vs_budget BY customer` |
| `risks` | *What are the main risks?* | Alert Center |
| `model_distribution`, `series_types`, `summary` | … | registries / profiling / overview |

Entities extracted: months (EN/PT names, Q1–Q4, "next month"), hierarchy members (customers, SKUs, product names,
regions, channels, categories, brands), dimensions, and what-if levers with signed percentages
("preço cair 5%" → price −5%).

## Semantic layer

Metrics: `actual, forecast, consensus, budget, target, wmape, accuracy, bias, gap_vs_budget, gap_vs_target, uplift,
fva, distribution, price, p10, p90`. Dimensions: `period, region, channel, customer, category, brand, sku, model,
scenario`. Each query is rendered as a readable string shown in the UI, e.g.
`SELECT wmape(units) BY sku WHERE all ORDER BY wmape DESC LIMIT 10`.

## Grounding guard

`allowed_numbers()` collects every number in the facts (also ×100, ÷10³, ÷10⁶ for %, K and M formats).
`grounding_violations()` rejects any number in the LLM text that is not within 1.5% of an allowed value (small
integers ≤ 31 and years are ignored). A rejected answer falls back to the deterministic narrative and the UI shows
*"LLM output rejected by grounding check"*.

## Local LLM

* Default model `llama3.2:3b` (configurable with `OLLAMA_MODEL`), URL `OLLAMA_URL`.
* `docker compose up` starts Ollama and pulls the model once.
* Without Ollama the analyst still works with the rule-based narrative (EN/PT), so the app has **no hard
  dependency on any LLM**.

## Dynamic charts

The analyst returns a chart spec rendered by the frontend `ChartRenderer`: `line`, `bar` (horizontal or vertical,
signed colors for bias/gaps), `waterfall`, plus KPI cards and tables.
