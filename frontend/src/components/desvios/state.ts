/**
 * URL state of the deviation deep dive (spec §2.3.2) and the response shapes it reads.
 *
 * History rules: drilling (adding to `path`), the breadcrumb, opening/closing `serie` and changing
 * `cmp` push a history entry (browser Back undoes them); `sel`, `periodo`, `medida`, `nivel` and
 * `causa` replace the current one.
 */
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import {
  DEFAULT_PERIOD,
  DIM_KEYS,
  LENS_OF,
  nextLevel,
  parseDeviationState,
  toSearchParams,
  type ChapterId,
  type Cmp,
  type DeviationUrlState,
  type DimKey,
  type Lente,
  type Medida,
  type Nivel,
} from "../../lib/deviationsUrl";
import type { Filters } from "../../types";
import type { DeviationFocus, DeviationSeries, DeviationSummary } from "../../types/deviations";

/* ------------------------------------------------------------- response extras */

/**
 * Response shapes the page reads. The backend's additive fields (bridge footnote, focus tags and
 * recurrence, the series card's recurrence line, availability and notices) are declared as optional
 * fields in `types/deviations.ts`.
 */
export type FocusPayload = DeviationFocus;
export type SeriesPayload = DeviationSeries;
export type SummaryPayload = DeviationSummary;

/* ------------------------------------------------------------------- labels */

export const DIM_LABEL: Record<DimKey, string> = {
  region: "Região",
  channel: "Canal",
  customer: "Cliente",
  category: "Categoria",
  brand: "Marca",
  sku: "SKU",
};

/** Short name of each report chapter, for "← Voltar ao relatório · {capítulo}". */
export const CHAPTER_SHORT: Record<ChapterId, string> = {
  resumo: "Resumo",
  realizado: "Realizado",
  precisao: "Precisão",
  projecao: "Próximos meses",
  gap: "Gap vs orçamento",
  meta: "Meta",
  decisoes: "Decisões",
};

/** Comparison labels used until the first summary arrives (the backend sends its own, with {h}). */
export const CMP_FALLBACK_LABEL: Record<Cmp, string> = {
  fc_pl: "Consenso × Orçamento · próximos meses",
  fc_tg: "Consenso × Meta · próximos meses",
  ac_pl: "Real × Orçamento · últimos 12 meses",
  ac_fc: "Real × Estatístico (campeão)",
  ac_cs: "Real × Consenso histórico (com ajustes)",
};

/** Names of the two sides of each comparison: reference (P / actual) and compared (X / forecast). */
export const SIDES: Record<Cmp, { reference: string; compared: string; delta: string }> = {
  fc_pl: { reference: "Orçamento", compared: "Consenso", delta: "Desvio" },
  fc_tg: { reference: "Meta", compared: "Consenso", delta: "Desvio" },
  ac_pl: { reference: "Orçamento", compared: "Real", delta: "Desvio" },
  ac_fc: { reference: "Real", compared: "Estatístico", delta: "Erro (previsto − real)" },
  ac_cs: { reference: "Real", compared: "Consenso histórico", delta: "Erro (previsto − real)" },
};

export const isDim = (n: string | null | undefined): n is DimKey => !!n && (DIM_KEYS as string[]).includes(n);
export const isMonthCode = (p: string | undefined): p is string => !!p && /^\d{4}-\d{2}$/.test(p);
export const isForecastCmp = (cmp: Cmp) => LENS_OF[cmp] === "previsao";

/** fc_pl/fc_tg share the horizon window and ac_fc/ac_cs the backtest window; ac_pl has its own. */
const windowOf = (cmp: Cmp) => DEFAULT_PERIOD[cmp];

/** The drill path plus the focused member (when the breakdown level is a dimension), as filters. */
export function focusFilters(state: DeviationUrlState, level: Nivel): Filters {
  const out: Filters = { ...state.path };
  if (state.sel && isDim(level)) out[level] = state.sel;
  return out;
}

/* ---------------------------------------------------------------- the hook */

export type HistoryMode = "push" | "replace";

export interface DeviationNav {
  state: DeviationUrlState;
  /** Breakdown level actually shown (`nivel`, or the next drill level of the path). */
  level: Nivel;
  /** Current query string (stable identity of the URL state). */
  search: string;
  update: (patch: Partial<DeviationUrlState>, mode: HistoryMode) => void;
  setLens: (lens: Lente, planCmp?: Cmp) => void;
  setCmp: (cmp: Cmp) => void;
  setPeriodo: (periodo: string | undefined) => void;
  setMedida: (medida: Medida) => void;
  setNivel: (nivel: Nivel) => void;
  /** Toggles `sel` (click on a member). */
  select: (key: string) => void;
  /** `path[level] = key`, next level, clears `sel`. */
  drill: (key: string) => void;
  resetPath: () => void;
  /** Removes `dim` and every later dimension. */
  removeDim: (dim: DimKey) => void;
  /** Keeps the path up to `dim` (inclusive). */
  goToDim: (dim: DimKey) => void;
  toggleCausa: (code: string | undefined) => void;
  openSerie: (seriesId: string) => void;
  closeSerie: () => void;
}

export function useDeviationState(): DeviationNav {
  const [sp, setSp] = useSearchParams();
  const search = sp.toString();
  const state = useMemo(() => parseDeviationState(new URLSearchParams(search)), [search]);
  const level: Nivel = state.nivel ?? nextLevel(state.path);

  const update = useCallback(
    (patch: Partial<DeviationUrlState>, mode: HistoryMode) =>
      setSp(toSearchParams({ ...state, ...patch }), { replace: mode === "replace" }),
    [state, setSp],
  );

  return useMemo<DeviationNav>(() => {
    /** `nivel` kept only when still valid for the lens and not a dimension already in the path. */
    const keepNivel = (cmp: Cmp, path: DeviationUrlState["path"]) => {
      const n = state.nivel;
      if (!n) return undefined;
      if ((n === "champion" || n === "series_type") && LENS_OF[cmp] !== "previsao") return undefined;
      if (isDim(n) && path[n]) return undefined;
      return n;
    };
    const cutPath = (dim: DimKey, inclusive: boolean) => {
      const idx = DIM_KEYS.indexOf(dim);
      const path: DeviationUrlState["path"] = {};
      for (const d of DIM_KEYS) {
        const i = DIM_KEYS.indexOf(d);
        if (state.path[d] && (i < idx || (inclusive && i === idx))) path[d] = state.path[d];
      }
      return path;
    };
    return {
      state,
      level,
      search,
      update,
      setLens: (lens, planCmp = "fc_pl") => {
        const cmp: Cmp = lens === "plano" ? planCmp : "ac_fc";
        if (LENS_OF[state.cmp] === lens && state.cmp === cmp) return;
        update(
          { cmp, periodo: undefined, sel: undefined, causa: undefined, nivel: keepNivel(cmp, state.path) },
          "push",
        );
      },
      setCmp: (cmp) => {
        if (cmp === state.cmp) return;
        const sameLens = LENS_OF[cmp] === LENS_OF[state.cmp];
        update(
          {
            cmp,
            periodo: windowOf(cmp) === windowOf(state.cmp) ? state.periodo : undefined,
            sel: sameLens ? state.sel : undefined,
            causa: sameLens ? state.causa : undefined,
            nivel: keepNivel(cmp, state.path),
          },
          "push",
        );
      },
      setPeriodo: (periodo) =>
        update(
          { periodo: periodo && periodo !== DEFAULT_PERIOD[state.cmp] ? periodo : undefined },
          "replace",
        ),
      setMedida: (medida) => update({ medida }, "replace"),
      setNivel: (nivel) => update({ nivel, sel: undefined }, "replace"),
      select: (key) => update({ sel: state.sel === key ? undefined : key }, "replace"),
      drill: (key) => {
        if (!isDim(level)) return;
        update({ path: { ...state.path, [level]: key }, nivel: undefined, sel: undefined }, "push");
      },
      resetPath: () => update({ path: {}, nivel: keepNivel(state.cmp, {}), sel: undefined }, "push"),
      removeDim: (dim) => {
        const path = cutPath(dim, false);
        update({ path, nivel: undefined, sel: undefined }, "push");
      },
      goToDim: (dim) => {
        const path = cutPath(dim, true);
        update({ path, nivel: undefined, sel: undefined }, "push");
      },
      toggleCausa: (code) => update({ causa: code && state.causa !== code ? code : undefined }, "replace"),
      openSerie: (seriesId) => {
        if (state.serie === seriesId) return;
        update({ serie: seriesId }, "push");
      },
      closeSerie: () => update({ serie: undefined }, "push"),
    };
  }, [state, level, search, update]);
}
