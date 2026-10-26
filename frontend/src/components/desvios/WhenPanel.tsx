/**
 * "Quando aconteceu?" (spec §2.3.4): month by month, the compared value in front of the reference
 * (top) and the Δ (bottom); in the Previsão lens, Real vs the forecast plus the signed error.
 * Clicking a month narrows the whole page to it (`periodo=YYYY-MM`); clicking it again, or
 * "Ver todos os meses", goes back to the comparison's default window.
 */
import { CalendarRange } from "lucide-react";

import { VarianceColumns } from "../../charts/VarianceColumns";
import { DEFAULT_PERIOD, LENS_OF } from "../../lib/deviationsUrl";
import { Card, ErrorState } from "../ui";
import { Skeleton } from "./common";
import { SIDES, isMonthCode, type DeviationNav, type FocusPayload } from "./state";

export const WHEN_QUESTION = "Quando aconteceu?";

export function WhenPanel({
  nav,
  focus,
  error,
  className,
}: {
  nav: DeviationNav;
  focus?: FocusPayload;
  error: Error | null;
  className?: string;
}) {
  const { state } = nav;
  const forecast = LENS_OF[state.cmp] === "previsao";
  const sides = SIDES[state.cmp];
  const month = isMonthCode(state.periodo) ? state.periodo : undefined;
  const onSelectMonth = (m: string) => nav.setPeriodo(m === month ? DEFAULT_PERIOD[state.cmp] : m);

  return (
    <Card
      data-visual="quando"
      data-question={WHEN_QUESTION}
      title={WHEN_QUESTION}
      className={className}
      // The chart legend already says "Clique em um mês para filtrar": not repeated here.
      subtitle={
        forecast
          ? `Real × ${sides.compared.toLowerCase()} mês a mês, em R$`
          : `${sides.compared} × ${sides.reference.toLowerCase()} mês a mês`
      }
      actions={
        month ? (
          <button
            type="button"
            className="btn-ghost px-3 py-1.5 text-[12.5px]"
            onClick={() => nav.setPeriodo(undefined)}
          >
            <CalendarRange size={14} aria-hidden /> Ver todos os meses
          </button>
        ) : undefined
      }
    >
      {error && !focus ? (
        <ErrorState error={error} />
      ) : !focus ? (
        <Skeleton height={320} />
      ) : focus.available === false || !focus.monthly?.length ? (
        <p className="py-10 text-center text-sm text-muted">
          {focus.reason ?? "Sem meses com dados neste recorte."}
        </p>
      ) : (
        <VarianceColumns
          rows={focus.monthly}
          mode={forecast ? "error" : "plan"}
          xKind={state.cmp === "ac_pl" ? "AC" : "FC"}
          xLabel={sides.compared}
          pLabel={forecast ? undefined : sides.reference}
          measure={forecast ? "revenue" : state.medida}
          quarters={forecast ? null : focus.quarters}
          selectedMonth={month}
          onSelectMonth={onSelectMonth}
          height={320}
          ariaLabel={
            forecast
              ? `Real e ${sides.compared.toLowerCase()} por mês, com o erro de previsão`
              : `${sides.compared} e ${sides.reference.toLowerCase()} por mês, com o desvio`
          }
        />
      )}
    </Card>
  );
}
