import type { Measure } from "../lib/format";

export type Filters = Partial<
  Record<"region" | "channel" | "customer" | "category" | "brand" | "sku", string>
>;

export interface TimelineRow {
  date: string;
  actual?: number | null;
  base?: number | null;
  consensus?: number | null;
  incremental?: number | null;
  p10?: number | null;
  p90?: number | null;
  challenger?: number | null;
  backtest?: number | null;
  budget?: number | null;
  target?: number | null;
}

export interface Totals {
  base?: number;
  consensus?: number;
  incremental?: number;
  sigma?: number;
  p10?: number;
  p90?: number;
  budget?: number;
  target?: number;
  actual_ltm: number;
  actual_prior_ltm: number;
}

export interface Job {
  run_id: string;
  dataset_version: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  step: string;
  created_at: string;
  horizon: number;
  done?: number;
  total?: number;
  duration_s?: number;
  message?: string;
  params?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  n_series?: number;
  n_models?: number;
  finished_at?: string;
  model_version?: string;
  scenario?: string;
}

export interface Issue {
  severity: "critical" | "warning" | "info";
  code: string;
  message: string;
  count: number;
  examples: unknown[];
}

export interface ValidationReport {
  status: "valid" | "warnings" | "blocked";
  can_forecast: boolean;
  blocking_message: string | null;
  summary: Record<string, any>;
  quality: {
    completeness: number;
    consistency: number;
    historical_depth: number;
    granularity: number;
    overall: number;
  };
  issues: Issue[];
  column_mapping: Record<string, string>;
  missing_optional: string[];
}

export interface DatasetInfo {
  dataset_version: string;
  name: string;
  source: string;
  file_name: string | null;
  created_at: string;
  n_rows: number;
  n_series: number;
  n_skus: number;
  n_customers: number;
  start_date: string;
  end_date: string;
  quality_score: number;
  quality_label?: string;
  status: string;
  is_active: boolean;
  plan_source: string;
  validation?: ValidationReport;
  metadata?: Record<string, any>;
  active_run?: string | null;
}

export interface SeriesRow {
  series_id: string;
  customer: string;
  sku: string;
  product: string;
  region: string;
  channel: string;
  category: string;
  brand: string;
  series_type?: string;
  champion?: string;
  challenger?: string;
  wmape?: number;
  bias?: number;
  accuracy?: number;
  bias_class?: string;
  confidence?: string;
  units_ltm?: number;
  revenue_ltm?: number;
  forecast_12m?: number;
  consensus_12m?: number;
  history_months?: number;
}

export interface LeaderRow {
  model: string;
  status?: string;
  family?: string;
  wmape: number | null;
  bias: number | null;
  rmse: number | null;
  mae?: number | null;
  mase?: number | null;
  rank: number | null;
  champion_flag?: boolean;
  challenger_flag?: boolean;
  fold_wmape?: number[];
  parameters?: Record<string, unknown>;
  series_evaluated?: number;
  champion_count?: number;
  challenger_count?: number;
  win_rate?: number;
  accuracy?: number;
  bias_class?: string;
  wmape_std?: number | null;
}

export interface Override {
  override_id: string;
  customer: string | null;
  sku: string | null;
  date: string;
  event_type: string;
  uplift_pct: number;
  comment: string;
  created_by: string;
  created_at: string;
  affected_series?: number;
  base_units?: number;
  incremental_units?: number;
}

export interface ScenarioParams {
  price_change_pct: number;
  distribution_change_pct: number;
  promo_months: string[];
  promo_discount_pct: number;
  merch_months: string[];
  marketing_change_pct: number;
  customer_growth_pct: number;
  market_growth_pct: number;
  scope: Filters;
  base: "consensus" | "statistical";
}

export interface Scenario {
  scenario_id: string;
  name: string;
  kind: "base" | "conservative" | "aggressive" | "custom";
  description: string;
  params: ScenarioParams;
  is_system: boolean;
  created_at: string;
  updated_at: string;
}

export interface Feasibility {
  available: boolean;
  message?: string;
  measure: Measure;
  months: string[];
  classification: "REALISTIC" | "STRETCH" | "AGGRESSIVE" | "UNDERESTIMATED";
  probability: number;
  target: number;
  budget: number;
  statistical: number;
  consensus: number;
  p10: number;
  p50: number;
  p90: number;
  planned_events: number;
  last_year: number;
  historical_growth: number | null;
  required_growth: number | null;
  forecast_growth: number | null;
  volatility_cv: number | null;
  potential_units: number | null;
  capacity_ratio: number | null;
  calibration: {
    required_incremental_vs_budget: number | null;
    gap_vs_consensus: number;
    gap_vs_consensus_pct: number | null;
    budget_vs_consensus_pct: number | null;
  };
  reasons: string[];
  levers: {
    lever: string;
    required_change: number | null;
    elasticity: number;
    note: string;
    plausible: boolean;
  }[];
  recommendation: string;
  curve?: { x: number; pdf: number; p_exceed: number }[];
  by_customer?: FeasibilityRow[];
}

export interface FeasibilityRow {
  member: string;
  target: number;
  budget: number;
  consensus: number;
  p10: number;
  p90: number;
  probability: number;
  classification: string;
  gap_vs_target: number;
  gap_vs_target_pct: number;
  required_growth: number | null;
}

export interface Alert {
  id: string;
  type: string;
  title: string;
  color: string;
  icon: string;
  severity: "critical" | "high" | "medium" | "low";
  entity: Record<string, string>;
  issue: string;
  magnitude: string;
  value: number | null;
  potential_impact: number | null;
  explanation: string;
  recommendation: string;
}

export interface ChartSpec {
  type: "line" | "bar" | "waterfall" | "scatter" | "heatmap" | "table" | "kpi";
  title?: string;
  format?: string;
  x?: string[];
  series?: { name: string; data: (number | null)[]; dashed?: boolean }[];
  horizontal?: boolean;
  kinds?: string[];
  highlight?: number;
}

export interface MetricCard {
  label: string;
  value: number | string | null;
  format: string;
  tone?: string;
  hint?: string;
}

export interface AiResponse {
  answer: string;
  insights: string[];
  metrics: MetricCard[];
  chart: ChartSpec | null;
  table: { columns: string[]; rows: unknown[][]; formats?: string[] } | null;
  recommendations: string[];
  filters: Filters;
  meta: {
    question: string;
    language: string;
    intent: Record<string, any> | null;
    engine: string;
    grounding: { checked: boolean; passed?: boolean; violations?: string[] };
    query: string | null;
    run_id: string | null;
    dataset_version: string;
    latency_ms: number;
  };
}
