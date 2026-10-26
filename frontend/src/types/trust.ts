/** `GET /api/models/trust` (spec §4.3.2): how much the forecast deserves credit. */

export type ConfidenceSplit = { High: number; Medium: number; Low: number };
export type VerdictCode = "confiavel" | "cautela" | "nao_confiavel";

export interface TrustRun {
  run_id: string;
  finished_at: string;
  duration_s: number;
  n_series: number;
  n_models: number;
  n_folds: number;
  fold_horizon: number;
  horizon: number;
  avg_candidates: number;
  backtest_start: string;
  backtest_end: string;
  n_fallback: number;
  /** "1–3 meses" (fold_horizon = 1 → "1 mês") */
  lag_label: string;
}

export interface TrustChampion {
  model: string;
  label: string;
  family: string;
  family_label: string;
  series: number;
  share: number;
  wmape_won: number | null;
  is_reference: boolean;
}

export interface TrustPattern {
  series_type: string;
  label: string;
  n: number;
  top_model: string;
  top_model_label: string;
  top_model_series: number;
}

export interface TrustBacktestMonth {
  date: string;
  actual: number;
  statistical: number;
  naive: number;
}

export interface TrustCaution {
  series_id: string;
  customer: string;
  sku: string;
  product: string;
  wmape: number | null;
  bias: number | null;
  confidence: string;
  series_type_label: string;
  revenue_12m: number;
}

export interface TrustVerdict {
  code: VerdictCode;
  label: string;
  headline: string;
  reasons: string[];
}

export interface Trust {
  available: boolean;
  reason?: string;
  run: TrustRun;
  accuracy: number;
  wmape: number;
  bias: number;
  bias_class: "Over" | "Under" | "Balanced";
  bias_label: string;
  naive_wmape: number | null;
  gain_vs_naive_pp: number | null;
  error_reduction_vs_naive: number | null;
  /** null without historical overrides */
  consensus_wmape: number | null;
  fva_pp: number | null;
  wmape_by_lag: { lag: number; wmape: number }[];
  confidence_series: ConfidenceSplit;
  confidence_revenue_share: ConfidenceSplit;
  /** every model with ≥ 1 win, desc */
  champions: TrustChampion[];
  by_pattern: TrustPattern[];
  pattern_insight: string;
  /** R$ */
  backtest_monthly: TrustBacktestMonth[];
  /** ≤ 5 */
  caution: TrustCaution[];
  verdict: TrustVerdict;
}

/** Answer of `GET /api/models/trust` while there is no completed run (spec §4.3.2). */
export interface TrustUnavailable {
  available: false;
  reason?: string;
}

/** Full response of `GET /api/models/trust`: the payload, or `available: false` with a pt-BR reason. */
export type TrustResponse = Trust | TrustUnavailable;

/** True when the trust payload carries numbers (a completed run exists). */
export const isTrustAvailable = (t: TrustResponse | null | undefined): t is Trust =>
  !!t && t.available === true;
