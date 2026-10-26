/**
 * Action dispatch of the deep dive (spec §2.3.4 action chips, §2.3.6 drawer bar, §4.4 "Actions").
 *
 * The backend sends `ActionSpec`s ({kind, label, prefill}); this module turns each kind into the
 * matching move: open the series card, open the adjustment modal, go to Cenários, ask the AI, open
 * the workspace or the FVA tab. Before leaving the page, "Perguntar à IA", "Simular cenário" and
 * "Abrir no workspace" copy the drill path into `useFilters` (spec §1.4), so the tools inherit it.
 */
import {
  CalendarPlus,
  ChartColumn,
  ChartLine,
  PanelRightOpen,
  Sparkles,
  SquareSplitHorizontal,
  type LucideIcon,
} from "lucide-react";
import { useCallback } from "react";
import { useNavigate } from "react-router-dom";

import { useFilters } from "../../hooks/useFilters";
import { DIM_KEYS } from "../../lib/deviationsUrl";
import { ROUTES, type ScenarioPrefill } from "../../lib/routes";
import type { Filters } from "../../types";
import type { ActionSpec } from "../../types/deviations";
import type { OverrideFormDefaults } from "../OverrideForm";

export type ActionKind = ActionSpec["kind"];

export const ACTION_ICON: Record<ActionKind, LucideIcon> = {
  open_series: PanelRightOpen,
  open_workspace: ChartLine,
  create_override: CalendarPlus,
  simulate: SquareSplitHorizontal,
  ask_ai: Sparkles,
  open_fva: ChartColumn,
};

/** Target of the "Criar ajuste comercial" modal. */
export interface OverrideTarget {
  customer: string;
  sku: string | null;
  defaults: OverrideFormDefaults;
}

type Prefill = Record<string, unknown>;

const str = (v: unknown): string | undefined => (typeof v === "string" && v.trim() ? v : undefined);
const num = (v: unknown): number | undefined => (typeof v === "number" && Number.isFinite(v) ? v : undefined);
const obj = (v: unknown): Prefill | undefined =>
  v && typeof v === "object" && !Array.isArray(v) ? (v as Prefill) : undefined;

/** Merges dimension filters from several sources (later sources win); other keys are ignored. */
export function filtersOf(...sources: (Prefill | Filters | null | undefined)[]): Filters {
  const out: Filters = {};
  for (const src of sources) {
    if (!src) continue;
    for (const d of DIM_KEYS) {
      const v = str((src as Prefill)[d]);
      if (v) out[d] = v;
    }
  }
  return out;
}

/** `ROUTES.cenarios` params from a simulate prefill ({scope:{dims}, <dims flat>, levers?}). */
export function scenarioPrefill(prefill: Prefill | undefined): ScenarioPrefill {
  const p = prefill ?? {};
  const dims = filtersOf(obj(p.scope), p);
  return {
    region: dims.region,
    channel: dims.channel,
    customer: dims.customer,
    category: dims.category,
    sku: dims.sku,
    distribution_change_pct: num(p.distribution_change_pct),
    price_change_pct: num(p.price_change_pct),
    marketing_change_pct: num(p.marketing_change_pct),
  };
}

/** Modal target from a create_override prefill ({customer, sku, date, event_type, uplift_pct, comment}). */
export function overrideTarget(prefill: Prefill | undefined): OverrideTarget | null {
  const p = prefill ?? {};
  const customer = str(p.customer);
  if (!customer) return null;
  return {
    customer,
    sku: str(p.sku) ?? null,
    defaults: {
      date: str(p.date),
      event_type: str(p.event_type),
      uplift_pct: num(p.uplift_pct),
      comment: str(p.comment),
    },
  };
}

/** The backend's probed AI question of an ask_ai action. */
export const aiQuestion = (a: ActionSpec | undefined): string | undefined =>
  a?.kind === "ask_ai" ? str(a.prefill?.question) : undefined;

const seriesIdOf = (p: Prefill | undefined) => str(p?.series_id);

export interface ActionRunnerOptions {
  /** Drill path + focused member: copied into `useFilters` before leaving the page. */
  filters: Filters;
  openSeries: (seriesId: string) => void;
  createOverride: (target: OverrideTarget) => void;
}

/** Returns `run(action)`, which performs an `ActionSpec`. */
export function useActionRunner({ filters, openSeries, createOverride }: ActionRunnerOptions) {
  const navigate = useNavigate();
  const setFilters = useFilters((s) => s.setFilters);
  return useCallback(
    (a: ActionSpec) => {
      const p = a.prefill;
      switch (a.kind) {
        case "open_series": {
          const id = seriesIdOf(p);
          if (id) openSeries(id);
          return;
        }
        case "create_override": {
          const target = overrideTarget(p);
          if (target) createOverride(target);
          return;
        }
        case "simulate": {
          setFilters(filtersOf(filters, obj(p?.scope)));
          navigate(ROUTES.cenarios(scenarioPrefill(p)));
          return;
        }
        case "ask_ai": {
          const q = str(p?.question);
          if (!q) return;
          setFilters(filtersOf(filters, obj(p?.filters)));
          navigate(ROUTES.ia(q));
          return;
        }
        case "open_workspace": {
          setFilters(filtersOf(filters));
          navigate(ROUTES.workspace(seriesIdOf(p)));
          return;
        }
        case "open_fva": {
          // Only an in-app route is followed; anything else falls back to the FVA tab.
          const route = str(p?.route);
          navigate(route?.startsWith("/app/") ? route : ROUTES.modelos("fva"));
          return;
        }
      }
    },
    [filters, openSeries, createOverride, navigate, setFilters],
  );
}
