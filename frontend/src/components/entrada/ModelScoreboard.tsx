/**
 * "Placar" of the model competition (spec §2.1, step 2): an HTML bar list, not a chart. One row per
 * model with at least one win (bar ∝ series won), the top 6, then "Outros {k} modelos · {s} séries".
 * Wins per model are compared instead of a cross-model WMAPE ranking, because each model only competes
 * on the demand patterns the router sends it. The naive method is the reference: gray, with a chip.
 */
import clsx from "clsx";
import { useId } from "react";

import { full, pct } from "../../lib/format";
import { t } from "../../lib/labels";
import type { TrustChampion } from "../../types/trust";
import { plural } from "./helpers";

export const SCOREBOARD_TOP = 6;
export const REFERENCE_TOOLTIP =
  "Quando o ingênuo vence, a série não tem padrão explorável (ex.: histórico curto).";

/** Display name (`t.model`); the reference keeps its catalogue name next to the word the page uses. */
function modelLabel(c: TrustChampion): string {
  const label = c.label || t.model(c.model);
  return c.is_reference && /^(naive|ingênuo)$/i.test(label) ? "Ingênuo (Naive)" : label;
}

interface Row {
  key: string;
  label: string;
  series: number;
  detail: string;
  kind: "model" | "reference" | "others";
}

function ReferenceChip() {
  const tipId = useId();
  return (
    <span className="group relative inline-flex">
      <span
        tabIndex={0}
        aria-describedby={tipId}
        className="inline-flex cursor-help items-center rounded-full bg-[#eef0f6] px-2 py-0.5 text-[10.5px] font-semibold text-ink-2 ring-1 ring-[#dfe3ee] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        referência
      </span>
      <span
        role="tooltip"
        id={tipId}
        className="pointer-events-none invisible absolute bottom-full left-0 z-20 mb-2 w-64 rounded-xl bg-white px-3 py-2 text-[12px] font-normal leading-snug text-ink-2 opacity-0 shadow-[0_12px_28px_-12px_rgba(45,50,119,0.4)] ring-1 ring-line transition group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100"
      >
        {REFERENCE_TOOLTIP}
      </span>
    </span>
  );
}

export function ModelScoreboard({
  champions,
  top = SCOREBOARD_TOP,
}: {
  /** `trust.champions`: every model with ≥ 1 win (any order; sorted here by series won). */
  champions: TrustChampion[];
  top?: number;
}) {
  const sorted = [...champions].sort((a, b) => b.series - a.series);
  // A single leftover model is shown by name: "Outros 1 modelo" would take the same row and say less.
  const cut = sorted.length <= top + 1 ? sorted.length : top;
  const shown = sorted.slice(0, cut);
  const rest = sorted.slice(cut);
  const rows: Row[] = shown.map((c) => ({
    key: c.model,
    label: modelLabel(c),
    series: c.series,
    detail: [
      `${full(c.series)} ${plural(c.series, "série", "séries")}`,
      pct(c.share, 0),
      c.wmape_won != null ? `erro ${pct(c.wmape_won, 1)} onde venceu` : null,
    ]
      .filter(Boolean)
      .join(" · "),
    kind: c.is_reference ? "reference" : "model",
  }));
  if (rest.length) {
    const s = rest.reduce((acc, c) => acc + c.series, 0);
    rows.push({
      key: "outros",
      label: `Outros ${rest.length} ${plural(rest.length, "modelo", "modelos")}`,
      series: s,
      detail: `${full(s)} ${plural(s, "série", "séries")}`,
      kind: "others",
    });
  }
  const max = Math.max(1, ...rows.map((r) => r.series));

  return (
    <ul aria-label="Placar: séries vencidas por modelo" className="space-y-2.5" data-testid="placar">
      {rows.map((r) => (
        <li
          key={r.key}
          data-row={r.kind}
          className="grid grid-cols-1 items-center gap-x-4 gap-y-1 sm:grid-cols-[minmax(150px,190px)_minmax(120px,1fr)] lg:grid-cols-[190px_minmax(120px,1fr)_minmax(250px,auto)]"
        >
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span
              className={clsx(
                "break-words text-[13.5px] font-semibold leading-snug",
                r.kind === "model" ? "text-ink" : "text-ink-2",
              )}
            >
              {r.label}
            </span>
            {r.kind === "reference" && <ReferenceChip />}
          </div>
          <div className="h-3 min-w-[120px] overflow-hidden rounded-full bg-[#f0f2f9]" aria-hidden>
            <div
              className={clsx(
                "h-full rounded-full",
                r.kind === "model" && "bg-gradient-to-r from-[#3483fa] to-[#5b9cff]",
                r.kind === "reference" && "bg-[#b4b9cc]",
                r.kind === "others" && "bg-[#d5daeb]",
              )}
              style={{ width: `${Math.max(2, (r.series / max) * 100)}%` }}
            />
          </div>
          <span className="text-[12.5px] leading-snug text-ink-2 tabular sm:col-start-2 lg:col-start-auto">
            {r.detail}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default ModelScoreboard;
