/**
 * Contracts of the deviation endpoints (spec §4.3.3), copied verbatim from the spec.
 * Types only: `/api/deviations/{summary,focus,exceptions,series}`.
 */
import type { Cmp } from "../lib/deviationsUrl";
import type { TimelineRow } from "./index";

export type { Cmp };

/* ------------------------------------------------------------------ summary */

export interface DeviationSummary {
  available: boolean;
  reason?: string;
  cmp: Cmp;
  lens: "plan" | "forecast";
  measure: "revenue" | "units";
  period: { code: string; label: string; months: string[]; kind: "future" | "history" | "backtest" };
  periods: { code: string; label: string }[];
  comparisons: { cmp: Cmp; label: string; available: boolean; reason?: string }[];
  node: { label: string; path: { dim: string; member: string; label: string }[]; n_series: number };
  headline: string;
  notices: string[];
  /** exactly 4 */
  kpis: KpiSpec[];
  breakdown: {
    level: string;
    level_label: string;
    next_level: string | null;
    levels: { value: string; label: string; disabled: boolean; reason?: string }[];
    rows: PlanRow[] | ErrorRow[];
    others: { n: number; value: number } | null;
    n_members: number;
  };
  concentration: { n_top: number; share: number; members: string[]; n_members: number } | null;
}

export interface KpiSpec {
  id: string;
  label: string;
  value: number | null;
  format: "currency" | "currency_signed" | "units" | "percent" | "percent_signed" | "pp" | "text";
  text?: string | null;
  delta?: string | null;
  delta_tone?: "good" | "bad" | "neutral";
  hint?: string | null;
}

export interface Tag {
  code: string;
  label: string;
}

export interface PlanRow {
  key: string;
  label: string;
  x: number;
  p: number;
  variance: number;
  variance_pct: number | null;
  share_of_adverse: number | null;
  share_of_favorable: number | null;
  cum_share: number | null;
  prob_hit: number | null;
  growth_plan: number | null;
  growth_fc: number | null;
  /** fc_* only: same member, ac_pl U12M (§4.2.2 recurrence) */
  realized_variance_pct: number | null;
  effects: { volume: number; mix: number | null; price: number | null; events: number | null };
  tags: Tag[];
  is_exception: boolean;
  n_series: number;
  drillable: boolean;
  series_id?: string;
}

export interface ErrorRow {
  key: string;
  label: string;
  actual: number;
  forecast: number;
  abs_error: number;
  net_error: number;
  wmape: number | null;
  bias: number | null;
  bias_class: "Over" | "Under" | "Balanced" | null;
  systematic: number;
  noise: number;
  share: number;
  cum_share: number;
  top_cause: (Tag & { group: string; share: number }) | null;
  is_exception: boolean;
  n_series: number;
  drillable: boolean;
  series_id?: string;
}

/* -------------------------------------------------------------------- focus */

export interface DeviationFocus {
  available: boolean;
  reason?: string;
  cmp: Cmp;
  lens: "plan" | "forecast";
  measure: "revenue" | "units";
  period: { code: string; label: string; months: string[]; kind: string };
  focus: { level: string | null; member: string | null; label: string };
  /** focus headline (= summary headline when no focus) */
  headline: string;
  /** plan */
  bridge: BridgeStep[] | null;
  /** plan */
  drivers: {
    plan_price_premium: number | null;
    price_promo: number | null;
    reg_price_gap: number | null;
    volume_split: { anticipated: number; surprise: number; uncovered: number; coverage: number } | null;
    events: { event_type: string; value: number; n: number }[];
    /** additive: realized/compared price vs the reference price, all months */
    avg_price_gap?: number | null;
  } | null;
  /** forecast */
  causes: CauseRow[] | null;
  split: { systematic: number; noise: number; systematic_share: number } | null;
  /** top 3 */
  by_model: { model: string; label: string; abs_error: number; share: number; wmape: number | null }[] | null;
  fva: { statistical_wmape: number | null; consensus_wmape: number | null; fva_pp: number | null } | null;
  monthly: MonthlyPlanRow[] | MonthlyErrorRow[];
  /** fc_* only (`code` = "t1".."t4", additive) */
  quarters: { label: string; start: string; end: string; variance: number; code?: string }[] | null;
  /** 2–3 pt-BR sentences */
  diagnosis: string[];
  actions: ActionSpec[];
  /* Additive fields sent by the backend beyond the §4.3.3 contract (optional). */
  /** plan, units: "Em unidades não há efeito preço/mix." */
  bridge_note?: string | null;
  /** plan: tags of the focused node/member */
  tags?: Tag[];
  /** plan: the bridge effects of the focus */
  effects?: { volume: number; mix: number | null; price: number | null; events: number | null } | null;
  /** fc_*: the focus' ac_pl V% over the last 12 months (recurrence) */
  realized_variance_pct?: number | null;
}

export interface BridgeStep {
  key: "reference" | "challenge" | "budget_subtotal" | "volume" | "mix" | "price" | "events" | "compared";
  label: string;
  value: number;
  kind: "total" | "subtotal" | "delta";
  notation?: "AC" | "PL" | "FC" | "TG";
  help: string;
}

export interface CauseRow {
  code: string;
  label: string;
  group: "controllable" | "inherent" | "unexplained";
  group_label: string;
  abs_error: number;
  share: number;
  net_error: number;
  direction: "over" | "under" | "mixed";
  n_cells: number;
  n_series: number;
}

export interface MonthlyPlanRow {
  date: string;
  x: number | null;
  p: number | null;
  py: number | null;
  target: number | null;
  low: number | null;
  high: number | null;
  variance: number | null;
  variance_pct: number | null;
}

export interface MonthlyErrorRow {
  date: string;
  actual: number;
  forecast: number;
  error: number;
  abs_error: number;
  wmape: number | null;
}

export interface ActionSpec {
  kind: "open_series" | "create_override" | "simulate" | "ask_ai" | "open_fva" | "open_workspace";
  label: string;
  prefill?: Record<string, unknown>;
}

/* --------------------------------------------------------------- exceptions */

export interface DeviationExceptions {
  total: number;
  rows: ExceptionRow[];
  /** additive: false (with a pt-BR `reason`) when the comparison is unavailable */
  available?: boolean;
  reason?: string;
}

export interface ExceptionRow {
  series_id: string;
  label: string;
  customer: string;
  sku: string;
  product: string;
  region: string;
  channel: string;
  category: string;
  /** R$, always ≥ 0 */
  impact: number;
  /* plan */
  x?: number;
  p?: number;
  variance?: number;
  variance_pct?: number | null;
  prob_hit?: number | null;
  /* forecast */
  abs_error?: number;
  wmape?: number | null;
  bias?: number | null;
  tracking_signal?: number | null;
  top_cause?: Tag | null;
  confidence: string | null;
  champion: string | null;
  series_type_label: string | null;
  tags: Tag[];
  recommended_action: { code: string; label: string };
  actions: ActionSpec[];
}

/* ------------------------------------------------------------------- series */

export interface DeviationSeries {
  series_id: string;
  label: string;
  header: {
    customer: string;
    sku: string;
    product: string;
    region: string;
    channel: string;
    category: string;
    series_type_label: string;
    confidence: string | null;
    champion: string | null;
    challenger: string | null;
  };
  summary: {
    reference: number | null;
    compared: number | null;
    variance: number | null;
    variance_pct: number | null;
    /** additive, plan fc_*: the series' ac_pl V% over the last 12 months ("Últimos 12 meses: …") */
    realized_variance_pct?: number | null;
    /** additive, plan fc_*: chance of reaching the reference */
    prob_hit?: number | null;
  };
  /** context.timeline(ctx, {customer, sku}, measure, 24) */
  timeline: TimelineRow[];
  /** forecast lens */
  evidence: EvidenceRow[] | null;
  /** plan lens */
  months: MonthlyPlanRow[] | null;
  effects: { volume: number; mix: number | null; price: number | null; events: number | null } | null;
  tags: Tag[];
  recommended_action: { code: string; label: string };
  actions: ActionSpec[];
  future_overrides: { date: string; event_type: string; uplift_pct: number; comment: string | null }[];
  /* Additive fields sent by the backend beyond the §4.3.3 contract (optional). */
  available?: boolean;
  reason?: string;
  notices?: string[];
  cmp?: Cmp;
  lens?: "plan" | "forecast";
  measure?: "revenue" | "units";
  period?: { code: string; label: string; months: string[]; kind: string };
}

export interface EvidenceRow {
  date: string;
  horizon_step: number;
  actual: number;
  forecast: number;
  error: number;
  error_pct: number | null;
  cause: Tag & { group: string };
  evidence: string;
}
