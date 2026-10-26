/**
 * Step 2 of the Entrada stage, "Competição de modelos" (spec §2.1, item 5): explainer, the run states
 * (none / running / failed) and, once the run completed, the headline, the scoreboard of wins per
 * model, the pattern insight and the facts line.
 */
import { TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { runProgressPct } from "../../hooks/useJourney";
import { full, pct, pp } from "../../lib/format";
import { ROUTES } from "../../lib/routes";
import type { JourneyStatus } from "../../types/journey";
import { isTrustAvailable, type Trust, type TrustResponse } from "../../types/trust";
import { RunForecastButton } from "../RunControls";
import { Card, ErrorState, ProgressBar } from "../ui";
import { durationLabel, explainerText, failedRunText, plural, RUN_DEFAULTS, stepAnchorId } from "./helpers";
import { ModelScoreboard } from "./ModelScoreboard";
import { Notice, Skeleton, ToggleButton } from "./shared";

function Headline({ trust }: { trust: Trust }) {
  const gain = trust.gain_vs_naive_pp;
  const tail =
    gain == null
      ? "."
      : gain > 0
        ? `, ${pp(gain)} a menos que o método ingênuo.`
        : `, ${pp(-gain)} a mais que o método ingênuo.`;
  return (
    <p className="break-words text-[16.5px] leading-relaxed text-ink-2" data-testid="competicao-manchete">
      <strong className="font-semibold text-ink">
        {full(trust.run.n_models)} modelos competiram em {full(trust.run.n_series)} séries
      </strong>
      ; o campeão de cada série erra <strong className="font-semibold text-ink">{pct(trust.wmape, 1)}</strong>
      {tail}
    </p>
  );
}

function Running({ run }: { run: JourneyStatus["run"] }) {
  const value = runProgressPct(run.progress);
  // No live region here: the step text changes on every poll (1,5 s) and would flood screen readers;
  // the progressbar below carries the value.
  return (
    <div className="rounded-2xl bg-[#f6f8fe] p-5 ring-1 ring-[#e9ecf6]">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <span className="text-[13.5px] font-semibold text-ink">Competição em andamento</span>
        <span className="text-[13.5px] font-bold text-brand-dark tabular">{value}%</span>
      </div>
      <div
        role="progressbar"
        aria-label="Progresso da competição de modelos"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
      >
        <ProgressBar value={value / 100} />
      </div>
      {run.step && <p className="mt-3 break-words text-[13px] leading-snug text-ink-2">{run.step}</p>}
      {run.done != null && run.total != null && (
        <p className="mt-1 text-[13px] font-semibold text-ink-2 tabular">
          {full(run.done)} de {full(run.total)} séries
        </p>
      )}
      <p className="mt-3 text-[12.5px] leading-relaxed text-muted">
        Leva cerca de 5 minutos na base de demonstração. O método ingênuo compete em todas as séries como
        referência mínima.
      </p>
    </div>
  );
}

function Completed({ trust, expanded, bodyId }: { trust: Trust; expanded: boolean; bodyId: string }) {
  const r = trust.run;
  return (
    <div className="space-y-5">
      <Headline trust={trust} />
      {expanded && (
        <div id={bodyId} className="space-y-5">
          <p className="text-[13px] leading-relaxed text-muted">{explainerText(r)}</p>
          <ModelScoreboard champions={trust.champions} />
          {trust.pattern_insight && (
            <p
              className="break-words text-[14px] font-medium leading-relaxed text-ink"
              data-testid="padrao-insight"
            >
              {trust.pattern_insight}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-[#eef0f7] pt-4">
            <span className="text-[12.5px] text-muted" data-testid="competicao-fatos">
              {full(r.n_models)} modelos · {full(r.avg_candidates, 1)} candidatos por série em média ·
              executado em {durationLabel(r.duration_s)}
            </span>
            <Link
              to={ROUTES.modelos("ranking")}
              className="text-[12.5px] font-semibold text-brand hover:text-brand-dark hover:underline"
            >
              Ver ranking completo
            </Link>
            {r.n_fallback > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-xl bg-amber-50 px-2.5 py-1 text-[12px] font-medium text-amber-900 ring-1 ring-amber-200/80">
                <TriangleAlert size={13} aria-hidden className="text-amber-600" />
                {full(r.n_fallback)} {plural(r.n_fallback, "série usou", "séries usaram")} o ingênuo como
                contingência
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function StepModels({
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
  const bodyId = `${stepAnchorId(2)}-corpo`;
  const ready = journey.stage === "pronto";
  const run = journey.run;
  const available = isTrustAvailable(trust) ? trust : null;

  let body;
  if (!journey.dataset) {
    body = (
      <div className="space-y-2">
        <p className="text-[13.5px] leading-relaxed text-ink-2">{explainerText(RUN_DEFAULTS)}</p>
        <p className="text-[13px] text-muted">A competição começa assim que a base for carregada.</p>
      </div>
    );
  } else if (!ready && run.state === "running") {
    body = (
      <div className="space-y-4">
        <p className="text-[13.5px] leading-relaxed text-ink-2">{explainerText(RUN_DEFAULTS)}</p>
        <Running run={run} />
      </div>
    );
  } else if (!ready && run.state === "failed") {
    body = (
      <div className="space-y-4">
        <ErrorState error={new Error(failedRunText(run.message))} />
        <RunForecastButton label="Tentar novamente" />
      </div>
    );
  } else if (!ready) {
    body = (
      <div className="space-y-4">
        <p className="text-[13.5px] leading-relaxed text-ink-2">{explainerText(RUN_DEFAULTS)}</p>
        <RunForecastButton />
      </div>
    );
  } else if (available) {
    body = <Completed trust={available} expanded={expanded} bodyId={bodyId} />;
  } else if (trustError) {
    body = <ErrorState error={trustError} />;
  } else if (trust && !trust.available) {
    body = <Notice tone="info" title={trust.reason ?? "O placar ainda não está disponível."} />;
  } else {
    // Skeleton at the final height (spec §2.0 rule 7): the one-line headline when collapsed (the
    // default once pronto), the headline plus the scoreboard when expanded.
    body = (
      <div className="space-y-3" aria-busy={trustLoading || undefined}>
        <Skeleton className="h-6 w-3/4" />
        {expanded && <Skeleton className="h-[340px]" />}
      </div>
    );
  }

  return (
    <Card
      id={stepAnchorId(2)}
      className="scroll-mt-24"
      data-visual="competicao"
      data-question="Quais modelos venceram — e com que margem?"
      title="Competição de modelos"
      subtitle="Quais modelos venceram — e com que margem?"
      actions={
        ready && available ? (
          <ToggleButton open={expanded} onToggle={onToggle} controls={bodyId} closedLabel="Ver placar" />
        ) : undefined
      }
    >
      {body}
    </Card>
  );
}

export default StepModels;
