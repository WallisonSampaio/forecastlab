/**
 * "Onde está o desvio?" (spec §2.3.4): the breakdown of the current cut as `VarianceBars`.
 * Click a row = focus it (`sel`, the other panels follow); "›", double click or Shift+Enter = drill
 * one level down. At the series level a click opens the series card instead.
 */
import { VarianceBars } from "../../charts/VarianceBars";
import { LENS_OF } from "../../lib/deviationsUrl";
import type { ErrorRow, PlanRow } from "../../types/deviations";
import { Card, ErrorState } from "../ui";
import { Skeleton } from "./common";
import { isDim, type DeviationNav, type SummaryPayload } from "./state";

export const WHERE_QUESTION = "Onde está o desvio?";

export function WherePanel({
  nav,
  summary,
  stale = false,
  error,
  className,
}: {
  nav: DeviationNav;
  /** Summary of the current comparison (undefined while loading). */
  summary?: SummaryPayload;
  /**
   * The rows on screen belong to the previous request (placeholder while refetching, e.g. right
   * after a drill): their members are of the previous level, so clicks are ignored until the new
   * breakdown arrives (a "›" would otherwise write a region name into `channel`).
   */
  stale?: boolean;
  error: Error | null;
  className?: string;
}) {
  const { state, level } = nav;
  const forecast = LENS_OF[state.cmp] === "previsao";
  const bd = summary?.breakdown;
  const atSeries = level === "series";
  const rows = (bd?.rows ?? []) as (PlanRow | ErrorRow)[];
  const byKey = new Map(rows.map((r) => [r.key, r]));
  const locked = stale || (!!bd && bd.level !== level);

  const unit = state.medida === "units" ? "unidades" : "receita (R$)";
  // The chart's own legend explains the encoding (solid/light, colours, click hints): not repeated here.
  const subtitle = bd
    ? forecast
      ? `Erro absoluto por ${bd.level_label.toLowerCase()}, em R$`
      : `Desvio por ${bd.level_label.toLowerCase()} em ${unit} · perdas primeiro, depois ganhos`
    : undefined;

  return (
    <Card
      data-visual="onde"
      data-question={WHERE_QUESTION}
      title={WHERE_QUESTION}
      subtitle={subtitle}
      className={className}
      aria-busy={locked || undefined}
    >
      {error && !summary ? (
        <ErrorState error={error} />
      ) : !bd ? (
        <Skeleton height={420} />
      ) : !rows.length ? (
        <p className="py-10 text-center text-sm text-muted">Nenhum membro com dados neste recorte.</p>
      ) : (
        <>
          {atSeries && (
            <p className="mb-2 text-[12px] text-muted">
              Clique em uma série para abrir a ficha com as evidências.
            </p>
          )}
          <VarianceBars
            rows={bd.rows}
            mode={forecast ? "error" : "plan"}
            measure={forecast ? "revenue" : state.medida}
            others={bd.others}
            selectedKey={atSeries ? state.serie : state.sel}
            onSelect={(key) => {
              if (locked) return;
              if (atSeries) nav.openSerie(byKey.get(key)?.series_id ?? key);
              else nav.select(key);
            }}
            onDrill={
              isDim(level)
                ? (key) => {
                    if (!locked) nav.drill(key);
                  }
                : undefined
            }
            ariaLabel={`${forecast ? "Erro de previsão" : "Desvio"} por ${bd.level_label.toLowerCase()}`}
          />
        </>
      )}
    </Card>
  );
}
