import { ChevronRight, CircleCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { money } from "../../lib/format";
import type { Decision } from "../../types/story";
import { decisionHref, impactBasisText, isAppRoute } from "./helpers";

/**
 * "Decisões" chapter table (spec §2.2.3, ≤ 5 rows): rank · decision with its evidence · impact with its
 * basis · owner · a link to where the decision is worked on. Text cells wrap; nothing is cut off.
 */
export function DecisionTable({ rows, horizonMonths }: { rows: Decision[]; horizonMonths: number }) {
  if (!rows.length) {
    return (
      <div className="flex items-center gap-3 rounded-2xl bg-emerald-50/80 px-4 py-4 text-sm text-emerald-900">
        <CircleCheck size={18} className="shrink-0" aria-hidden />
        Nenhuma decisão crítica neste ciclo — plano alinhado.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="table-base">
        <caption className="sr-only">Decisões para a reunião de S&OP, da maior para a menor</caption>
        <thead>
          <tr>
            <th scope="col" className="w-10">
              <span aria-hidden>#</span>
              <span className="sr-only">Ordem</span>
            </th>
            <th scope="col">Decisão</th>
            <th scope="col" className="text-right">
              Impacto
            </th>
            <th scope="col">Responsável</th>
            <th scope="col">
              <span className="sr-only">Onde agir</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((d, i) => {
            const href = decisionHref(d.link.route);
            const linkClass =
              "inline-flex items-center gap-0.5 whitespace-nowrap rounded-lg px-2 py-1 text-[12.5px] font-semibold text-brand transition hover:bg-[#eef4ff] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/60";
            return (
              <tr key={d.code} data-decision={d.code} className="align-top">
                <td className="align-top">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#1b1f3b] text-[12px] font-bold tabular-nums text-white">
                    {i + 1}
                  </span>
                </td>
                <td className="min-w-[260px] whitespace-normal align-top">
                  <div className="break-words text-[14px] font-semibold leading-snug text-ink">
                    {d.decision}
                  </div>
                  <div className="mt-1 break-words text-[12.5px] leading-relaxed text-muted">
                    {d.evidence}
                  </div>
                </td>
                <td className="align-top text-right">
                  <div className="text-[15px] font-bold tabular-nums text-ink">{money(d.impact)}</div>
                  <div className="ml-auto mt-0.5 max-w-[150px] whitespace-normal text-[11.5px] leading-snug text-muted">
                    {impactBasisText(d.impact_basis, horizonMonths)}
                  </div>
                </td>
                <td className="min-w-[150px] whitespace-normal align-top text-[13px] text-ink-2">
                  {d.owner}
                </td>
                <td className="align-top text-right">
                  {isAppRoute(href) ? (
                    <Link to={href} className={linkClass}>
                      {d.link.label}
                      <ChevronRight size={14} aria-hidden />
                    </Link>
                  ) : (
                    <a href={href} className={linkClass}>
                      {d.link.label}
                      <ChevronRight size={14} aria-hidden />
                    </a>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default DecisionTable;
