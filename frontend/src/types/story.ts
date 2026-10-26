/** `GET /api/story` (spec §4.5): the 7-chapter executive report, all chapters in one payload. */
import type { ChapterId, DeviationUrlState } from "../lib/deviationsUrl";
import type { BridgeStep, CauseRow, KpiSpec, MonthlyPlanRow, PlanRow } from "./deviations";

export type { ChapterId };

export type VisualKind =
  | "kpis"
  | "bridge"
  | "cause_bars"
  | "monthly_variance"
  | "variance_bars"
  | "feasibility_range"
  | "decision_table";

export interface StoryReference {
  cycle_label: string;
  last_actual: string;
  horizon_label: string;
  horizon_months: number;
  ltm_label: string;
  backtest_label: string;
  lag_label: string;
  scope_label: string;
  dataset_version: string;
  run_id: string;
  plan_source: string | null;
  plan_derived: boolean;
  has_plan: boolean;
}

export interface Story {
  available: boolean;
  reason?: string;
  reference: StoryReference;
  governing_thought: string;
  scqa: { situacao: string; complicacao: string; resposta: string };
  /** exactly 7, fixed order */
  chapters: Chapter[];
}

export interface Takeaway {
  text: string;
  link?: { label: string; params: Partial<DeviationUrlState> } | null;
}

export interface Chapter {
  id: ChapterId;
  index: number;
  title: string;
  short: string;
  question: string;
  headline: string;
  context: string;
  /** ≤ 3 */
  takeaways: Takeaway[];
  status: "ok" | "empty";
  notice: string | null;
  /** `data` is null when `status` is "empty" (the frame then shows `notice` instead of the visual). */
  visual: { kind: VisualKind; data: unknown };
  investigate: { label: string; params: Partial<DeviationUrlState> } | null;
  secondary_action: { label: string; route: string } | null;
  ask_ai: string | null;
  /** the numbers the headline/visual use (single source; tested) */
  facts: Record<string, number | string | null>;
}

export interface Decision {
  code: "D1" | "D2" | "D3" | "D4" | "D5" | "D6" | "D7" | "D8";
  decision: string;
  short: string;
  evidence: string;
  impact: number;
  impact_basis: "horizonte" | "backtest_anualizado";
  owner: string;
  link: { label: string; route: string };
}

/* ------------------------------------------------- `visual.data` per kind (§4.5) */

export interface KpisVisualData {
  cards: KpiSpec[];
}

export interface BridgeVisualData {
  steps: BridgeStep[];
  note: string;
}

export interface CauseBarsVisualData {
  causes: CauseRow[];
  total_abs_error: number;
  note: string;
}

export interface MonthlyVarianceVisualData {
  x_kind: "FC";
  rows: MonthlyPlanRow[];
  quarters: { label: string; start: string; end: string; variance: number }[] | null;
  x_label: string;
  p_label: string;
}

export interface VarianceBarsVisualData {
  /** ≤ 8 */
  rows: PlanRow[];
  others: { n: number; value: number } | null;
  level: string;
  level_label: string;
}

/** From `assess()` (sop/feasibility.py). */
export interface FeasibilityRangeVisualData {
  p10: number;
  p50: number;
  p90: number;
  target: number;
  budget: number;
  consensus: number;
  probability: number;
  classification: "REALISTIC" | "STRETCH" | "AGGRESSIVE" | "UNDERESTIMATED";
  display: { color: string; label: string; emoji?: string };
}

export interface DecisionTableVisualData {
  rows: Decision[];
}

/** Narrowing helper: `const d = chapter.visual.data as VisualDataOf<"bridge">`. */
export interface VisualDataByKind {
  kpis: KpisVisualData;
  bridge: BridgeVisualData;
  cause_bars: CauseBarsVisualData;
  monthly_variance: MonthlyVarianceVisualData;
  variance_bars: VarianceBarsVisualData;
  feasibility_range: FeasibilityRangeVisualData;
  decision_table: DecisionTableVisualData;
}
export type VisualDataOf<K extends VisualKind> = VisualDataByKind[K];
