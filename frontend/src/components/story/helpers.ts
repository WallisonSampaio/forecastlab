/**
 * Non-visual helpers of the executive report (spec §2.2): links, report scope and chart titles.
 *
 * - Chapter links keep the report scope and, while presenting, `?apresentacao=1`.
 * - Deep-dive links carry the chapter's params, the report scope in the path and `de=<chapter>`;
 *   they never carry `apresentacao`, so the deep dive opens in the normal shell (spec §1.6).
 */
import {
  DIM_KEYS,
  deviationsHref,
  type ChapterId,
  type DeviationUrlState,
  type DimKey,
} from "../../lib/deviationsUrl";
import {
  mergeSearch,
  PRESENTATION_PARAM,
  REPORT_SCOPE_DIMS,
  ROUTES,
  type ReportScope,
  type ReportScopeDim,
} from "../../lib/routes";
import type { Chapter, Decision, Story, VisualDataOf, VisualKind } from "../../types/story";

/* ------------------------------------------------------------------------- links */

/** "/app/relatorio/gap?region=Sul" (+ "&apresentacao=1" while presenting). */
export function chapterHref(id: ChapterId, scope: ReportScope, presenting = false): string {
  const base = ROUTES.relatorio(id, scope);
  return presenting ? mergeSearch(base, `?${PRESENTATION_PARAM}=1`) : base;
}

/**
 * Deep-dive link from the report: `params` + the report scope merged into `path` + `de`.
 * A breakdown level already fixed by the scope (e.g. `nivel=region` with `region=Sul`) is dropped,
 * together with its selected member, because the deep dive cannot break a node down by it.
 */
export function deepDiveHref(
  params: Partial<DeviationUrlState> | null | undefined,
  scope: ReportScope,
  de?: ChapterId,
): string {
  const path: DeviationUrlState["path"] = { ...(params?.path ?? {}), ...scope };
  const next: Partial<DeviationUrlState> = { ...(params ?? {}), path };
  if (de) next.de = de;
  const nivel = next.nivel;
  if (nivel && (DIM_KEYS as string[]).includes(nivel) && path[nivel as DimKey]) {
    delete next.nivel;
    delete next.sel;
  }
  return deviationsHref(next);
}

/** Decision-row route (built by the backend); a deep-dive route also learns where it came from. */
export function decisionHref(route: string, de: ChapterId = "decisoes"): string {
  if (!route.startsWith("/app/desvios")) return route;
  return mergeSearch(route, `?de=${de}`);
}

/** True for routes the router can open in-app ("/app/…"); anything else is a plain link. */
export const isAppRoute = (route: string) => route.startsWith("/");

/* ------------------------------------------------------------------------- scope */

/** pt-BR label of each report scope dimension. */
export const SCOPE_DIM_LABEL: Record<ReportScopeDim, string> = {
  region: "Região",
  channel: "Canal",
  category: "Categoria",
};

/** The scope's single dimension and member, or null for "Empresa toda". */
export function scopeEntry(scope: ReportScope): { dim: ReportScopeDim; member: string } | null {
  for (const dim of REPORT_SCOPE_DIMS) {
    const member = scope[dim];
    if (member) return { dim, member };
  }
  return null;
}

/* -------------------------------------------------------------------------- text */

/** "Base … · execução … · orçamento: … · erro de previsão medido em backtest fora da amostra (…)." */
export function disclosureText(ref: Story["reference"]): string {
  const plan = ref.plan_source ?? (ref.has_plan ? "informado na base" : "sem orçamento nesta base");
  return (
    `Base ${ref.dataset_version} · execução ${ref.run_id} · orçamento: ${plan} · ` +
    `erro de previsão medido em backtest fora da amostra (${ref.lag_label} de antecedência).`
  );
}

/** Muted line under each decision impact (spec §4.5): impacts are on different bases, never summed. */
export function impactBasisText(basis: Decision["impact_basis"], horizonMonths: number): string {
  return basis === "backtest_anualizado"
    ? "erro anualizado da janela de backtest"
    : `nos próximos ${horizonMonths} ${horizonMonths === 1 ? "mês" : "meses"}`;
}

/** `chapter.visual.data` narrowed to its kind (`{}` when the backend sends null, as for empty chapters). */
export const visualData = <K extends VisualKind>(chapter: Chapter) =>
  (chapter.visual.data ?? {}) as VisualDataOf<K>;

/** "Cliente" -> "cliente", "SKU" stays "SKU" (acronyms keep their case inside a sentence). */
export function lowerLabel(label: string): string {
  if (!label || label === label.toUpperCase()) return label;
  return label.charAt(0).toLowerCase() + label.slice(1);
}

/** Short descriptive title of each chapter visual (the chapter H1 already states the conclusion). */
export function visualTitle(chapter: Chapter): string {
  switch (chapter.visual.kind) {
    case "bridge":
      // Chapter "Realizado": Orçamento U12M (PL) → Volume → Mix → Preço → Real U12M (AC), spec §4.5.
      return "Do orçamento ao realizado: volume, mix e preço";
    case "cause_bars":
      return "Erro do forecast por causa";
    case "monthly_variance": {
      const d = visualData<"monthly_variance">(chapter);
      return `${d.x_label || "Consenso"} × ${d.p_label || "Orçamento"}, mês a mês`;
    }
    case "variance_bars":
      return `Desvio vs orçamento por ${lowerLabel(visualData<"variance_bars">(chapter).level_label || "Cliente")}`;
    case "feasibility_range":
      return "Faixa provável do consenso × orçamento × meta";
    case "decision_table":
      return "Decisões para a reunião";
    default:
      return "Indicadores do ciclo";
  }
}
