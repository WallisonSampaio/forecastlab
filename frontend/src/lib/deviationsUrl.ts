/**
 * URL contract of the deviation deep dive (`/app/desvios?…`, spec §2.3.2).
 * Owned by F1; consumed by the report (F4), the deep dive (F5), Entrada (F3) and the tools (F6).
 */
import type { Params } from "../services/api";

export type Cmp = "fc_pl" | "fc_tg" | "ac_pl" | "ac_fc" | "ac_cs";
/** Derived from cmp, also written to the URL for readability. */
export type Lente = "plano" | "previsao";
export type DimKey = "region" | "channel" | "customer" | "category" | "brand" | "sku";
/** champion / series_type: Previsão lens only, not drillable. */
export type Nivel = DimKey | "series" | "champion" | "series_type";
export type ChapterId = "resumo" | "realizado" | "precisao" | "projecao" | "gap" | "meta" | "decisoes";
export type Medida = "revenue" | "units";

export interface DeviationUrlState {
  cmp: Cmp;
  /** h | t1..t4 | u12m | bt | YYYY-MM ; undefined = DEFAULT_PERIOD[cmp] */
  periodo?: string;
  /** Ignored in Previsão. */
  medida: Medida;
  path: Partial<Record<DimKey, string>>;
  /** undefined = nextLevel(path) */
  nivel?: Nivel;
  /** Selected member of `nivel` (cross-highlight). */
  sel?: string;
  /** Previsão: filters the exceptions table by top cause. */
  causa?: string;
  /** Open drawer (series_id "Cliente|SKU"). */
  serie?: string;
  /** Origin chapter. */
  de?: ChapterId;
}

export const CMPS: Cmp[] = ["fc_pl", "fc_tg", "ac_pl", "ac_fc", "ac_cs"];
export const DIM_KEYS: DimKey[] = ["region", "channel", "customer", "category", "brand", "sku"];
export const CHAPTER_IDS: ChapterId[] = [
  "resumo",
  "realizado",
  "precisao",
  "projecao",
  "gap",
  "meta",
  "decisoes",
];
export const LENS_OF: Record<Cmp, Lente> = {
  fc_pl: "plano",
  fc_tg: "plano",
  ac_pl: "plano",
  ac_fc: "previsao",
  ac_cs: "previsao",
};
/** Default comparison of each lens (switching lens resets cmp to it). */
export const LENS_DEFAULT_CMP: Record<Lente, Cmp> = { plano: "fc_pl", previsao: "ac_fc" };
export const DEFAULT_CMP: Cmp = "fc_pl";
export const DEFAULT_PERIOD: Record<Cmp, string> = {
  fc_pl: "h",
  fc_tg: "h",
  ac_pl: "u12m",
  ac_fc: "bt",
  ac_cs: "bt",
};
export const DRILL_ORDER: DimKey[] = ["region", "channel", "customer", "category", "sku"];

const PLAN_LEVELS: Nivel[] = [...DIM_KEYS, "series"];
const FORECAST_LEVELS: Nivel[] = [...PLAN_LEVELS, "champion", "series_type"];
const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
const DAY = /^\d{4}-(0[1-9]|1[0-2])-\d{2}$/;

/**
 * Period code as written in the URL: trimmed, lower case, and a month given as an ISO day
 * ("2026-12-01", the date format of every chart row) shortened to "YYYY-MM", as the backend does.
 */
export function normalizePeriod(periodo: string | null | undefined): string | undefined {
  const p = periodo?.trim().toLowerCase();
  if (!p) return undefined;
  return DAY.test(p) ? p.slice(0, 7) : p;
}

/** First DRILL_ORDER key absent from path, else "series". */
export function nextLevel(path: DeviationUrlState["path"]): Nivel {
  return DRILL_ORDER.find((d) => !path[d]) ?? "series";
}

/** Period codes accepted for a comparison (the month itself is checked by the backend). */
export function isPeriodFor(cmp: Cmp, periodo: string): boolean {
  if (MONTH.test(periodo)) return true;
  if (cmp === "fc_pl" || cmp === "fc_tg") return periodo === "h" || /^t[1-9]\d?$/.test(periodo);
  if (cmp === "ac_pl") return periodo === "u12m";
  return periodo === "bt";
}

const isCmp = (v: string | null): v is Cmp => !!v && (CMPS as string[]).includes(v);
const nonEmpty = (v: string | null | undefined) => (v != null && v.trim() !== "" ? v : undefined);

/** URL -> normalised state. Invalid values fall back to defaults; "lente=previsao" without cmp -> "ac_fc". */
export function parseDeviationState(sp: URLSearchParams): DeviationUrlState {
  const rawCmp = sp.get("cmp");
  const cmp: Cmp = isCmp(rawCmp) ? rawCmp : sp.get("lente") === "previsao" ? "ac_fc" : DEFAULT_CMP;
  const lens = LENS_OF[cmp];

  const path: DeviationUrlState["path"] = {};
  for (const d of DIM_KEYS) {
    const v = nonEmpty(sp.get(d));
    if (v) path[d] = v;
  }

  const state: DeviationUrlState = {
    cmp,
    medida: sp.get("medida") === "units" ? "units" : "revenue",
    path,
  };

  const periodo = normalizePeriod(sp.get("periodo"));
  if (periodo && periodo !== DEFAULT_PERIOD[cmp] && isPeriodFor(cmp, periodo)) state.periodo = periodo;

  const nivel = sp.get("nivel") as Nivel | null;
  const levels = lens === "previsao" ? FORECAST_LEVELS : PLAN_LEVELS;
  // A dimension already fixed in the path cannot be the breakdown level.
  const alreadyFiltered = !!nivel && (DIM_KEYS as string[]).includes(nivel) && !!path[nivel as DimKey];
  if (nivel && levels.includes(nivel) && nivel !== nextLevel(path) && !alreadyFiltered) state.nivel = nivel;

  const sel = nonEmpty(sp.get("sel"));
  if (sel) state.sel = sel;
  const causa = nonEmpty(sp.get("causa"));
  if (causa && lens === "previsao") state.causa = causa;
  const serie = nonEmpty(sp.get("serie"));
  if (serie) state.serie = serie;
  const de = sp.get("de");
  if (de && (CHAPTER_IDS as string[]).includes(de)) state.de = de as ChapterId;
  return state;
}

/**
 * State -> URL params, omitting defaults. Key order:
 * lente, cmp, periodo, medida, region, channel, customer, category, brand, sku, nivel, sel, causa, serie, de.
 * `lente` is written only for the Previsão lens (Plano is the default) and `cmp` only when it is not fc_pl.
 */
export function toSearchParams(s: Partial<DeviationUrlState>): URLSearchParams {
  const cmp = s.cmp ?? DEFAULT_CMP;
  const path = s.path ?? {};
  const q = new URLSearchParams();
  if (LENS_OF[cmp] === "previsao") q.set("lente", "previsao");
  if (cmp !== DEFAULT_CMP) q.set("cmp", cmp);
  const periodo = normalizePeriod(s.periodo);
  if (periodo && periodo !== DEFAULT_PERIOD[cmp]) q.set("periodo", periodo);
  if (s.medida && s.medida !== "revenue") q.set("medida", s.medida);
  for (const d of DIM_KEYS) {
    const v = path[d];
    if (v) q.set(d, v);
  }
  if (s.nivel && s.nivel !== nextLevel(path)) q.set("nivel", s.nivel);
  if (s.sel) q.set("sel", s.sel);
  if (s.causa) q.set("causa", s.causa);
  if (s.serie) q.set("serie", s.serie);
  if (s.de) q.set("de", s.de);
  return q;
}

/** "a=1&b=x%20y" (spaces as %20, like every other route builder in lib/routes.ts). */
export function encodeParams(q: URLSearchParams): string {
  return [...q.entries()].map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&");
}

/** "/app/desvios?…" */
export function deviationsHref(s: Partial<DeviationUrlState>): string {
  const qs = encodeParams(toSearchParams(s));
  return qs ? `/app/desvios?${qs}` : "/app/desvios";
}

/** Query params of the /api/deviations/* calls: {cmp, period, measure, level, ...path}. */
export function apiParams(s: DeviationUrlState): Params {
  return {
    cmp: s.cmp,
    period: normalizePeriod(s.periodo) ?? DEFAULT_PERIOD[s.cmp],
    measure: LENS_OF[s.cmp] === "previsao" ? "revenue" : s.medida,
    level: s.nivel ?? nextLevel(s.path),
    ...s.path,
  };
}
