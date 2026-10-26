/**
 * Route builders of the app (spec §5 F1). Every link of the journey and the tools is built here,
 * so query-string rules (omitted empties, "%20" for spaces) stay the same everywhere.
 */
import { CHAPTER_IDS, deviationsHref, type ChapterId } from "./deviationsUrl";

type QueryValue = string | number | boolean | null | undefined;

/** "?a=1&b=x%20y" from ordered key/values; empty values are skipped. */
export function qs(params?: Record<string, QueryValue>): string {
  if (!params) return "";
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join("&")}` : "";
}

/**
 * `to` + the query string `search` ("?a=1"), merged. Keys already in `to` win; the current URL's other
 * keys are appended. `mergeSearch("/app/models?tab=fva", "?region=Sul")` -> "/app/models?tab=fva&region=Sul".
 */
export function mergeSearch(to: string, search: string): string {
  const extra = search.startsWith("?") ? search.slice(1) : search;
  if (!extra) return to;
  const q = to.indexOf("?");
  if (q < 0) return `${to}?${extra}`;
  const own = new URLSearchParams(to.slice(q + 1));
  const kept = extra.split("&").filter((pair) => {
    if (!pair) return false;
    const raw = pair.split("=", 1)[0].replace(/\+/g, " ");
    let key = raw;
    try {
      key = decodeURIComponent(raw);
    } catch {
      /* malformed escape typed by hand ("%E0%A4"): compare the raw key, never crash the redirect */
    }
    return !own.has(key);
  });
  return kept.length ? `${to}&${kept.join("&")}` : to;
}

/* ------------------------------------------------------------------ report scope (§1.4) */

export type ReportScopeDim = "region" | "channel" | "category";
export type ReportScope = Partial<Record<ReportScopeDim, string>>;
export const REPORT_SCOPE_DIMS: ReportScopeDim[] = ["region", "channel", "category"];
/** sessionStorage key where the report keeps its last scope (read/write in try/catch). */
export const REPORT_SCOPE_STORAGE_KEY = "fl.report.scope";

/** Report scope from the URL: one dimension, one member, or none (the first of region|channel|category). */
export function reportScopeFromSearch(sp: URLSearchParams): ReportScope {
  for (const dim of REPORT_SCOPE_DIMS) {
    const v = sp.get(dim)?.trim();
    if (v) return { [dim]: v };
  }
  return {};
}

/** Saves the report scope for the session (an empty scope clears it). Never throws. */
export function saveReportScope(scope: ReportScope): void {
  try {
    const clean = reportScopeFromSearch(new URLSearchParams(qs(scope)));
    if (Object.keys(clean).length) sessionStorage.setItem(REPORT_SCOPE_STORAGE_KEY, JSON.stringify(clean));
    else sessionStorage.removeItem(REPORT_SCOPE_STORAGE_KEY);
  } catch {
    /* storage unavailable (private mode, blocked): the URL stays the source of truth */
  }
}

/** Last report scope of the session ({} when none or unreadable). Never throws. */
export function loadReportScope(): ReportScope {
  try {
    const raw = sessionStorage.getItem(REPORT_SCOPE_STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    const sp = new URLSearchParams();
    for (const dim of REPORT_SCOPE_DIMS) {
      const v = (parsed as Record<string, unknown>)[dim];
      if (typeof v === "string") sp.set(dim, v);
    }
    return reportScopeFromSearch(sp);
  } catch {
    return {};
  }
}

/** `capitulo` URL segment -> a valid chapter (unknown -> "resumo"). */
export const chapterOrDefault = (cap: string | undefined): ChapterId =>
  cap && (CHAPTER_IDS as string[]).includes(cap) ? (cap as ChapterId) : "resumo";

/* --------------------------------------------------------------- presentation mode (§1.6) */

/** `?apresentacao=1` on `/app/relatorio/*` hides the sidebar, topbar and footer. */
export const PRESENTATION_PARAM = "apresentacao";
export const isReportPath = (pathname: string) =>
  pathname === "/app/relatorio" || pathname.startsWith("/app/relatorio/");

/* ------------------------------------------------------------------------------ builders */

export interface WorkspacePrefill {
  mes?: string;
  evento?: string;
  uplift?: number;
  comentario?: string;
}

export interface ScenarioPrefill {
  region?: string;
  channel?: string;
  customer?: string;
  category?: string;
  sku?: string;
  distribution_change_pct?: number;
  price_change_pct?: number;
  marketing_change_pct?: number;
}

export type ModelsTab = "ranking" | "series" | "fva" | "registro";
export type DataTab = "versoes" | "diagnostico";

const SCENARIO_KEYS: (keyof ScenarioPrefill)[] = [
  "region",
  "channel",
  "customer",
  "category",
  "sku",
  "distribution_change_pct",
  "price_change_pct",
  "marketing_change_pct",
];

export const ROUTES = {
  /** "/app/entrada" | "/app/entrada?acao=carregar" */
  entrada: (o?: { acao?: "carregar" }) => `/app/entrada${qs({ acao: o?.acao })}`,
  /** "/app/relatorio/resumo?region=Sul" */
  relatorio: (cap: ChapterId = "resumo", scope?: ReportScope) =>
    `/app/relatorio/${cap}${qs({ region: scope?.region, channel: scope?.channel, category: scope?.category })}`,
  desvios: deviationsHref,
  /** "/app/forecasting?series=X" and, with a prefill, "&ajuste=1&mes=…&evento=…&uplift=…&comentario=…" */
  workspace: (seriesId?: string, p?: WorkspacePrefill) =>
    `/app/forecasting${qs({
      series: seriesId,
      ajuste: p ? 1 : undefined,
      mes: p?.mes,
      evento: p?.evento,
      uplift: p?.uplift,
      comentario: p?.comentario,
    })}`,
  /** "/app/scenarios?customer=Litoral%20Market&distribution_change_pct=0.1" */
  cenarios: (p?: ScenarioPrefill) =>
    `/app/scenarios${qs(Object.fromEntries(SCENARIO_KEYS.map((k) => [k, p?.[k]])))}`,
  /** "/app/ai?q=A%20meta%20%C3%A9%20realista%3F" */
  ia: (q: string) => `/app/ai${qs({ q })}`,
  modelos: (tab?: ModelsTab) => `/app/models${qs({ tab })}`,
  bases: (tab?: DataTab) => `/app/data${qs({ tab })}`,
  alertas: () => "/app/alerts",
};

/**
 * Key of the shell's `<main>`: the first two path segments ("/app/relatorio", "/app/desvios", …), so
 * chapter changes inside `/app/relatorio/:capitulo` keep the report mounted (spec §1.2).
 */
export const sectionKey = (pathname: string) => pathname.split("/").slice(0, 3).join("/");
