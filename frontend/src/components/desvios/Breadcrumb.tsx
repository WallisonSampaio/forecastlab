/**
 * Drill path of the deep dive (spec §2.3.3): "Empresa toda › Região: Nordeste × › Canal: Varejo ×".
 * "Empresa toda" resets the path; a crumb's name goes back to that level; its × removes that
 * dimension and every later one. On the right, "Agrupar por" picks the breakdown level.
 */
import clsx from "clsx";
import { ChevronRight, X } from "lucide-react";
import { useId } from "react";

import { DIM_KEYS, type Nivel } from "../../lib/deviationsUrl";
import { DIM_LABEL, type DeviationNav, type SummaryPayload } from "./state";

const FALLBACK_LEVELS: { value: Nivel; label: string }[] = [
  ...DIM_KEYS.map((d) => ({ value: d as Nivel, label: DIM_LABEL[d] })),
  { value: "series", label: "Série" },
];

const lowerFirst = (s: string) => s.replace(/^./, (c) => c.toLowerCase());

export function Breadcrumb({ nav, summary }: { nav: DeviationNav; summary?: SummaryPayload }) {
  const { state, level } = nav;
  const groupId = useId();
  const crumbs = DIM_KEYS.filter((d) => state.path[d]).map((d) => ({ dim: d, member: state.path[d]! }));

  const levels =
    summary && summary.cmp === state.cmp && summary.breakdown?.levels?.length
      ? summary.breakdown.levels
      : FALLBACK_LEVELS.map((l) => ({ ...l, disabled: false, reason: undefined as string | undefined }));
  const hasLevel = levels.some((l) => l.value === level);

  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
      <nav aria-label="Recorte" className="min-w-0 flex-1">
        <ol className="flex flex-wrap items-center gap-x-1.5 gap-y-2 text-[13px]">
          <li>
            {crumbs.length ? (
              <button
                type="button"
                onClick={nav.resetPath}
                className="rounded-lg px-2 py-1 font-semibold text-brand transition hover:bg-white/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                Empresa toda
              </button>
            ) : (
              <span aria-current="page" className="px-2 py-1 font-semibold text-ink">
                Empresa toda
              </span>
            )}
          </li>
          {crumbs.map((c, i) => {
            const last = i === crumbs.length - 1;
            const text = `${DIM_LABEL[c.dim]}: ${c.member}`;
            return (
              <li key={c.dim} className="flex min-w-0 items-center gap-1.5">
                <ChevronRight size={14} aria-hidden className="shrink-0 text-muted" />
                <span
                  className={clsx(
                    "inline-flex min-w-0 max-w-full items-center gap-0.5 rounded-full border py-0.5 pl-1 pr-0.5",
                    last ? "border-[#c9dcff] bg-[#eaf2ff]" : "border-line bg-white/80",
                  )}
                >
                  {last ? (
                    <span
                      aria-current="page"
                      className="min-w-0 break-words px-2 py-0.5 font-semibold text-ink"
                    >
                      {text}
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => nav.goToDim(c.dim)}
                      className="min-w-0 break-words rounded-full px-2 py-0.5 text-left font-semibold text-ink-2 transition hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                    >
                      {text}
                    </button>
                  )}
                  <button
                    type="button"
                    aria-label={`Remover ${text}`}
                    title="Remover este filtro e os seguintes"
                    onClick={() => nav.removeDim(c.dim)}
                    className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-ink-2 transition hover:bg-white hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                  >
                    <X size={13} aria-hidden />
                  </button>
                </span>
              </li>
            );
          })}
        </ol>
      </nav>

      <div className="flex items-center gap-2">
        <label htmlFor={groupId} className="label-xs whitespace-nowrap">
          Agrupar por
        </label>
        <select
          id={groupId}
          className="input w-auto max-w-[260px] py-2 pr-9 text-[13px] font-medium"
          value={level}
          onChange={(e) => nav.setNivel(e.target.value as Nivel)}
        >
          {!hasLevel && <option value={level}>{level}</option>}
          {levels.map((l) => (
            <option key={l.value} value={l.value} disabled={l.disabled && l.value !== level}>
              {l.disabled && l.reason ? `${l.label} — ${lowerFirst(l.reason)}` : l.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
