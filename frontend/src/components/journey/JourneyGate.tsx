import { ArrowRight, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { runProgressLine, runProgressPct, useJourney } from "../../hooks/useJourney";
import { ROUTES } from "../../lib/routes";
import { failedRunText } from "../entrada/helpers";
import type { JourneyStatus } from "../../types/journey";
import { EmptyState, ProgressBar } from "../ui";

function GateBody({ journey }: { journey: JourneyStatus }) {
  const { stage, run } = journey;
  if (stage === "dados") {
    return (
      <p>
        Carregue uma base (ou a demonstração) e deixe os modelos competirem. Leva cerca de 5 minutos na base
        de demonstração.
      </p>
    );
  }
  if (run.state === "running") {
    const pct = runProgressPct(run.progress);
    const counted = run.done != null && run.total != null;
    return (
      <div className="w-full min-w-[260px] max-w-sm text-left">
        <div
          role="progressbar"
          aria-label="Progresso da competição de modelos"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
        >
          <ProgressBar value={pct / 100} />
        </div>
        {counted && run.step && <p className="mt-2 break-words text-xs text-ink-2">{run.step}</p>}
        <p className="mt-1 text-xs font-semibold tabular-nums text-ink-2">{runProgressLine(run)}</p>
      </div>
    );
  }
  if (run.state === "failed") {
    // The backend message already reads "A execução falhou: …"; never double the prefix.
    return <p className="break-words">{failedRunText(run.message)}</p>;
  }
  return <p>A base está pronta; falta rodar a competição de modelos.</p>;
}

/**
 * Rendered by Relatório and Desvios whenever `stage !== "pronto"` (spec §1.5):
 *
 *   const { data: journey } = useJourney();
 *   if (journey && journey.stage !== "pronto") return <JourneyGate journey={journey} />;
 *
 * Without the `journey` prop the gate reads `useJourney()` itself.
 */
export function JourneyGate({ journey }: { journey?: JourneyStatus | null }) {
  const own = useJourney({ enabled: !journey });
  const status = journey ?? own.data;
  return (
    <section className="card" data-journey-gate={status?.stage ?? "carregando"}>
      <EmptyState title="Antes do relatório, a confiança" icon={<ShieldCheck />}>
        <div className="flex flex-col items-center gap-4">
          {status && <GateBody journey={status} />}
          <Link to={ROUTES.entrada()} className="btn-primary">
            Ir para a Entrada <ArrowRight size={16} />
          </Link>
        </div>
      </EmptyState>
    </section>
  );
}

export default JourneyGate;
