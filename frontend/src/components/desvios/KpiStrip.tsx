/**
 * KPI strip of the deep dive (spec §2.3.4): the 4 cards the backend builds (`summary.kpis`),
 * rendered generically, without icons (spec §2.0 rule 2). Text values wrap instead of overflowing.
 */
import { formatKpi } from "../../lib/format";
import type { KpiSpec } from "../../types/deviations";
import { ErrorState, KpiCard } from "../ui";
import { Skeleton } from "./common";

export const KPI_QUESTION = "Quão grande, provável e concentrado é o desvio — e o que o explica?";

/** Long text values ("Demanda intermitente ou volátil") wrap at a smaller size; numbers stay on one line. */
function KpiValue({ spec }: { spec: KpiSpec }) {
  const text = formatKpi(spec);
  if (spec.format !== "text") return <>{text}</>;
  return (
    <span
      className={
        text.length > 16
          ? "block whitespace-normal break-words text-[1.15rem] leading-snug"
          : "block whitespace-normal break-words"
      }
    >
      {text}
    </span>
  );
}

export function KpiStrip({
  kpis,
  loading,
  error,
}: {
  kpis: KpiSpec[] | undefined;
  loading: boolean;
  error: Error | null;
}) {
  return (
    <section
      data-visual="kpis"
      data-question={KPI_QUESTION}
      aria-label="Indicadores do desvio"
      aria-busy={loading || undefined}
      className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
    >
      {error && !kpis?.length ? (
        <div className="sm:col-span-2 xl:col-span-4">
          <ErrorState error={error} />
        </div>
      ) : !kpis?.length ? (
        [0, 1, 2, 3].map((i) => <Skeleton key={i} height={118} className="rounded-3xl" />)
      ) : (
        kpis
          .slice(0, 4)
          .map((k) => (
            <KpiCard
              key={k.id}
              label={k.label}
              value={<KpiValue spec={k} />}
              delta={k.delta ?? undefined}
              deltaTone={k.delta_tone ?? "neutral"}
              hint={k.hint ?? undefined}
            />
          ))
      )}
    </section>
  );
}
