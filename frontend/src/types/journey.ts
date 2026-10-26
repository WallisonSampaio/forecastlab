/** `GET /api/journey` (spec §4.3.1): the single source of the journey state. */

export type JourneyStage = "dados" | "modelos" | "pronto";
export type JourneyRunState = "none" | "running" | "failed" | "completed";

export interface JourneyDataset {
  version: string;
  name: string;
  status: "valid" | "warnings" | "blocked";
  quality_score: number | null;
  quality_label: string | null;
  n_series: number;
  n_customers: number;
  n_skus: number;
  start_date: string;
  end_date: string;
  n_months: number;
  plan_source: string | null;
  plan_derived: boolean;
  has_plan: boolean;
  n_critical: number;
  n_warnings: number;
  has_overrides_history: boolean;
}

export interface JourneyRun {
  state: JourneyRunState;
  run_id: string | null;
  progress: number | null;
  step: string | null;
  done: number | null;
  total: number | null;
  message: string | null;
  finished_at: string | null;
  duration_s: number | null;
  rerunning: boolean;
}

export interface JourneyStatus {
  stage: JourneyStage;
  dataset: null | JourneyDataset;
  run: JourneyRun;
}
