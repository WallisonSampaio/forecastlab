/**
 * Step 3 of the Entrada stage, "Confiança no forecast" (spec §2.1, item 6): the verdict surface, four
 * KPI cards without icons, the out-of-sample backtest line, the "Onde ter cautela" list and the exit
 * buttons. Accuracy is measured in units, impact in R$.
 */
import clsx from "clsx";
import { ArrowRight, Lock, ShieldAlert, ShieldCheck, TriangleAlert, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";

import { BacktestLine } from "../../charts/BacktestLine";
import { deviationsHref } from "../../lib/deviationsUrl";
import { full, money, monthLabel, pct, pp } from "../../lib/format";
import { t } from "../../lib/labels";
import { ROUTES } from "../../lib/routes";
import type { JourneyStatus } from "../../types/journey";
import { isTrustAvailable, type Trust, type TrustResponse, type VerdictCode } from "../../types/trust";
import { Card, ConfidenceBadge, ErrorState, IconTile, KpiCard } from "../ui";
import { lagSentence, MAX_CAUTION, plural, stepAnchorId, VERDICT_LABEL } from "./helpers";
import { Notice, Skeleton, ToggleButton } from "./shared";

export const BACKTEST_TITLE = "Real vs previsto fora da amostra (R$)";

const VERDICT_STYLE: Record<
  VerdictCode,
  { Icon: LucideIcon; tone: "green" | "yellow" | "red"; box: string }
> = {
  confiavel: {
    Icon: ShieldCheck,
    tone: "green",
    box: "bg-gradient-to-br from-[#f3fcf7] to-[#e3f7ec] ring-emerald-200/70",
  },
  cautela: {
    Icon: TriangleAlert,
    tone: "yellow",
    box: "bg-gradient-to-br from-[#fffcf0] to-[#fff4d1] ring-amber-200/80",
  },
  nao_confiavel: {
    Icon: ShieldAlert,
    tone: "red",
    box: "bg-gradient-to-br from-[#fff7f7] to-[#fdeaea] ring-red-200/80",
  },
};

function Verdict({ trust }: { trust: Trust }) {
  const v = trust.verdict;
  const code: VerdictCode = v.code in VERDICT_STYLE ? v.code : "nao_confiavel";
  const s = VERDICT_STYLE[code];
  return (
    <div
      data-testid="veredito"
      data-verdict={code}
      className={clsx("flex items-start gap-4 rounded-3xl p-5 ring-1 sm:p-6", s.box)}
    >
      <IconTile icon={<s.Icon />} tone={s.tone} size="md" />
      <div className="min-w-0 flex-1">
        <p className="break-words text-[18px] font-bold leading-snug tracking-tight text-ink">
          {VERDICT_LABEL[code]}
        </p>
        {v.headline && (
          <p className="mt-1.5 break-words text-[14px] leading-relaxed text-ink-2">{v.headline}</p>
        )}
        {v.reasons.length > 0 && (
          <ul className="mt-2.5 list-disc space-y-1 pl-4 text-[12.5px] leading-relaxed text-ink-2">
            {v.reasons.map((r) => (
              <li key={r} className="break-words">
                {r}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Kpis({ trust }: { trust: Trust }) {
  const gain = trust.gain_vs_naive_pp;
  const share = trust.confidence_revenue_share;
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid="kpis-confianca">
      <KpiCard
        label="Acurácia fora da amostra"
        value={pct(trust.accuracy, 1)}
        hint={`WMAPE ${pct(trust.wmape, 1)} · em unidades`}
      />
      <KpiCard
        label="Viés"
        value={pct(trust.bias, 1, true)}
        delta={trust.bias_label || t.bias(trust.bias_class)}
        deltaTone={trust.bias_class === "Balanced" ? "neutral" : "bad"}
        hint="positivo = superestimou"
      />
      <KpiCard
        label="Ganho vs método ingênuo"
        value={gain == null ? "—" : pp(gain)}
        hint={
          trust.naive_wmape == null ? (
            "sem referência do método ingênuo"
          ) : (
            <span className={clsx(gain != null && gain <= 0 && "font-semibold text-red-700")}>
              ingênuo {pct(trust.naive_wmape, 1)} → estatístico {pct(trust.wmape, 1)}
            </span>
          )
        }
      />
      <KpiCard
        label="Receita prevista com confiança alta"
        value={pct(share.High, 0)}
        hint={`${full(trust.confidence_series.High)} de ${full(trust.run.n_series)} séries`}
      />
    </div>
  );
}

function Backtest({ trust }: { trust: Trust }) {
  const r = trust.run;
  const lag = lagSentence(trust.wmape_by_lag, r.fold_horizon);
  return (
    <section aria-label={BACKTEST_TITLE} className="rounded-3xl bg-white/70 p-5 ring-1 ring-[#e9ecf6]">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h4 className="text-[14.5px] font-semibold text-ink">{BACKTEST_TITLE}</h4>
        <span className="text-[12px] text-muted">
          {full(r.n_folds)} {plural(r.n_folds, "janela", "janelas")} de {full(r.fold_horizon)}{" "}
          {plural(r.fold_horizon, "mês", "meses")} · {monthLabel(r.backtest_start)}–
          {monthLabel(r.backtest_end)} · antecedência de {r.lag_label}
        </span>
      </div>
      <BacktestLine rows={trust.backtest_monthly} ariaLabel={BACKTEST_TITLE} height={260} />
      {lag && (
        <p className="mt-3 text-[13px] leading-relaxed text-ink-2" data-testid="erro-por-antecedencia">
          {lag}
        </p>
      )}
    </section>
  );
}

function Caution({ trust }: { trust: Trust }) {
  const rows = trust.caution.slice(0, MAX_CAUTION);
  const months = trust.run.horizon || 12;
  return (
    <section aria-labelledby="entrada-cautela-titulo">
      <h4 id="entrada-cautela-titulo" className="text-[14.5px] font-semibold text-ink">
        Onde ter cautela
      </h4>
      <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted">
        Séries com confiança baixa ou erro de 35% ou mais, as de maior receita prevista primeiro.
      </p>
      {rows.length === 0 ? (
        <p className="mt-3 rounded-2xl bg-[#f6f8fe] px-4 py-3 text-[13px] text-ink-2">
          Nenhuma série pede cautela: todas têm confiança média ou alta e erro abaixo de 35%.
        </p>
      ) : (
        <ul className="mt-3 space-y-2" data-testid="cautela">
          {rows.map((c) => (
            <li
              key={c.series_id}
              className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-2xl bg-white/85 px-4 py-3 ring-1 ring-[#eceff8]"
            >
              <span className="min-w-0 flex-1 basis-[260px] break-words text-[13.5px] font-medium leading-snug text-ink">
                {c.customer} · <span className="whitespace-nowrap">{c.sku}</span> {c.product}
              </span>
              <span className="inline-flex items-center gap-1.5 text-[12px] text-muted">
                Confiança <ConfidenceBadge value={c.confidence} />
              </span>
              <span className="text-[12.5px] text-ink-2 tabular">WMAPE {pct(c.wmape, 1)}</span>
              <span className="text-[12.5px] text-ink-2 tabular">
                Receita {months}M {money(c.revenue_12m)}
              </span>
              <span className="text-[12.5px] text-muted">{t.seriesType(c.series_type_label)}</span>
              <Link
                to={deviationsHref({
                  cmp: "ac_fc",
                  path: { customer: c.customer, sku: c.sku },
                  nivel: "series",
                  serie: c.series_id,
                })}
                className="inline-flex items-center gap-1 text-[12.5px] font-semibold text-brand hover:text-brand-dark hover:underline"
                aria-label={`Investigar ${c.customer} · ${c.sku}`}
              >
                Investigar <ArrowRight size={14} aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function TrustActions({ verdict }: { verdict?: VerdictCode }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Link className="btn-primary" to={ROUTES.relatorio("resumo")} data-testid="abrir-relatorio">
        {verdict === "nao_confiavel" ? "Abrir o relatório mesmo assim" : "Abrir o relatório"}
        <ArrowRight size={16} aria-hidden />
      </Link>
      <Link className="btn-secondary" to={ROUTES.modelos()}>
        Ver governança dos modelos
      </Link>
    </div>
  );
}

export function StepTrust({
  journey,
  trust,
  trustLoading,
  trustError,
  expanded,
  onToggle,
}: {
  journey: JourneyStatus;
  trust?: TrustResponse;
  trustLoading: boolean;
  trustError: Error | null;
  expanded: boolean;
  onToggle: () => void;
}) {
  const bodyId = `${stepAnchorId(3)}-corpo`;
  const ready = journey.stage === "pronto";
  const available = isTrustAvailable(trust) ? trust : null;

  let body;
  if (!ready) {
    body = (
      <div className="flex items-start gap-3 rounded-2xl bg-[#f6f8fe] px-4 py-3.5 text-[13.5px] leading-relaxed text-ink-2">
        <Lock size={16} aria-hidden className="mt-0.5 shrink-0 text-muted" />
        <span>
          O veredito aparece aqui ao fim da competição de modelos: acurácia fora da amostra, viés, ganho sobre
          o método ingênuo e as séries que pedem cautela.
        </span>
      </div>
    );
  } else if (available) {
    body = (
      <div className="space-y-6">
        <Verdict trust={available} />
        {expanded && (
          <div id={bodyId} className="space-y-6">
            <Kpis trust={available} />
            <Backtest trust={available} />
            <Caution trust={available} />
          </div>
        )}
        <TrustActions verdict={available.verdict.code} />
      </div>
    );
  } else if (trustError) {
    body = (
      <div className="space-y-4">
        <ErrorState error={trustError} />
        <TrustActions />
      </div>
    );
  } else if (trust && !trust.available) {
    body = <Notice tone="info" title={trust.reason ?? "O veredito ainda não está disponível."} />;
  } else {
    body = (
      <div className="space-y-6" aria-busy={trustLoading || undefined}>
        <Skeleton className="h-[120px] rounded-3xl" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-[104px] rounded-3xl" />
          ))}
        </div>
        <Skeleton className="h-[340px] rounded-3xl" />
      </div>
    );
  }

  return (
    <Card
      id={stepAnchorId(3)}
      className="scroll-mt-24"
      data-visual="confianca"
      data-question="Posso levar este número para a reunião?"
      title="Confiança no forecast"
      subtitle="Posso levar este número para a reunião?"
      actions={available ? <ToggleButton open={expanded} onToggle={onToggle} controls={bodyId} /> : undefined}
    >
      {body}
    </Card>
  );
}

export default StepTrust;
