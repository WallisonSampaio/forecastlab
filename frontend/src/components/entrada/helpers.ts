/** Pure helpers of the Entrada stage (spec §2.1). */
import { full, pct } from "../../lib/format";
import type { VerdictCode } from "../../types/trust";

/** DOM id of each step card (the stepper scrolls to it). */
export const stepAnchorId = (id: 1 | 2 | 3) => `entrada-passo-${id}`;

/** RunParams defaults, shown before the first run (spec §2.1, step 2 explainer). */
export const RUN_DEFAULTS = { n_models: 15, n_folds: 4, fold_horizon: 3 } as const;

export const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

/** "4 min 54 s" · "38 s" · "1 h 02 min" (run duration). */
export function durationLabel(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h} h ${String(m).padStart(2, "0")} min`;
  const rest = s % 60;
  return rest ? `${m} min ${rest} s` : `${m} min`;
}

/** "Cada série testa só os modelos plausíveis…" with the run's params (RunParams defaults before a run). */
export function explainerText(p: { n_models: number; n_folds: number; fold_horizon: number }): string {
  return `Cada série testa só os modelos plausíveis para o seu padrão (de ${full(p.n_models)} disponíveis) em ${full(
    p.n_folds,
  )} janelas fora da amostra de ${full(p.fold_horizon)} ${plural(
    p.fold_horizon,
    "mês",
    "meses",
  )}; vence o menor WMAPE, depois o menor viés.`;
}

/**
 * pt-BR text of a failed run. The backend already stores "A execução falhou: {erro}", so the message is
 * shown as is (no "A última execução falhou: A execução falhou: …").
 */
export function failedRunText(message: string | null | undefined): string {
  const m = message?.trim();
  if (!m) return "A última execução falhou.";
  return /falh/i.test(m) ? m : `A última execução falhou: ${m}`;
}

/** "Onde ter cautela" shows at most this many series (spec §2.1, step 3). */
export const MAX_CAUTION = 5;

/** Verdict label by code (spec §2.1, step 3: the code sets both the colour and the label). */
export const VERDICT_LABEL: Record<VerdictCode, string> = {
  confiavel: "Confiável para decisão",
  cautela: "Use com cautela — trate o número como faixa P10–P90",
  nao_confiavel: "Não confiável — revise a base antes de decidir",
};

/** Short verdict under the stepper node. */
export const VERDICT_SHORT: Record<VerdictCode, string> = {
  confiavel: "Confiável para decisão",
  cautela: "Use com cautela",
  nao_confiavel: "Não confiável",
};

/**
 * "O erro vai de 13,3% (1 mês de antecedência) a 14,8% (3 meses)." — null when the backtest has a single
 * lag (fold horizon 1) or the lags are missing. The lead times come from the lags actually measured.
 */
export function lagSentence(byLag: { lag: number; wmape: number }[], foldHorizon: number): string | null {
  const lags = [...byLag].filter((l) => Number.isFinite(l.wmape)).sort((a, b) => a.lag - b.lag);
  if (foldHorizon <= 1 || lags.length < 2) return null;
  const first = lags[0];
  const last = lags[lags.length - 1];
  const months = (n: number) => `${full(n)} ${plural(n, "mês", "meses")}`;
  return `O erro vai de ${pct(first.wmape, 1)} (${months(first.lag)} de antecedência) a ${pct(
    last.wmape,
    1,
  )} (${months(last.lag)}).`;
}
