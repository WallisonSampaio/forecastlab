/**
 * "Por que o forecast errou?" (spec §2.3.4 Previsão, report chapter "Precisão"): an HTML bar list
 * of root causes grouped as Controlável (brand) / Inerente (gray) / Sem causa (light hatch).
 * Each bar shows R$ and share of the absolute error plus the net direction in words
 * (superestimou / subestimou / direção mista). With `onSelect`, rows are toggle buttons.
 */
import clsx from "clsx";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

import { ChartFrame } from "../components/ui";
import { money, pct } from "../lib/format";
import { CAUSE_GROUP_ORDER, CAUSE_GROUP_STYLE, FOCUS_RING, IBCS } from "../lib/ibcs";
import { t } from "../lib/labels";
import type { CauseRow } from "../types/deviations";

export interface CauseBarsProps {
  causes: CauseRow[];
  selected?: string;
  onSelect?: (code: string) => void;
  ariaLabel: string;
  /** Optional footnote (e.g. the "Precisão" chapter's `visual.data.note`). */
  note?: string;
}

const DIRECTION = {
  over: { Icon: ArrowUp, color: IBCS.over, text: "superestimou" },
  under: { Icon: ArrowDown, color: IBCS.under, text: "subestimou" },
  mixed: { Icon: ArrowUpDown, color: IBCS.muted, text: "direção mista" },
} as const;

const styleOf = (group: string) => CAUSE_GROUP_STYLE[group] ?? CAUSE_GROUP_STYLE.unexplained;

export function CauseBars({ causes, selected, onSelect, ariaLabel, note }: CauseBarsProps) {
  const maxShare = Math.max(0, ...causes.map((c) => c.share)) || 1;
  const knownGroups: string[] = [...CAUSE_GROUP_ORDER];
  const groups = [
    ...CAUSE_GROUP_ORDER,
    ...Array.from(new Set(causes.map((c) => c.group))).filter((g) => !knownGroups.includes(g)),
  ]
    .map((g) => ({
      group: g,
      rows: causes.filter((c) => c.group === g).sort((a, b) => b.abs_error - a.abs_error),
    }))
    .filter((g) => g.rows.length > 0);
  const ordered = groups.flatMap((g) => g.rows);

  return (
    <ChartFrame
      ariaLabel={ariaLabel}
      columns={[
        { label: "Causa" },
        { label: "Grupo" },
        { label: "Erro (R$)", align: "right" },
        { label: "Participação", align: "right" },
        { label: "Direção" },
        { label: "Meses-série", align: "right" },
      ]}
      rows={ordered.map((c) => ({
        key: c.code,
        cells: [
          c.label,
          c.group_label || t.causeGroup(c.group),
          money(c.abs_error),
          pct(c.share, 0),
          t.errorDirection(c.direction),
          c.n_cells.toLocaleString("pt-BR"),
        ],
      }))}
      legend={onSelect && <span className="text-muted">Clique em uma causa para filtrar as séries</span>}
      note={note}
    >
      <div aria-label={ariaLabel} role="group" className="flex flex-col gap-4">
        {groups.map(({ group, rows }) => {
          const style = styleOf(group);
          const label = rows[0]?.group_label || style.label;
          const share = rows.reduce((s, r) => s + r.share, 0);
          const value = rows.reduce((s, r) => s + r.abs_error, 0);
          return (
            <section key={group} aria-label={`${label}: ${pct(share, 0)} do erro`}>
              <div className="mb-1 flex flex-wrap items-baseline justify-between gap-x-3 px-3">
                <span className="label-xs">{label}</span>
                <span className="tabular text-[12px] font-semibold text-ink-2">
                  {pct(share, 0)} do erro · {money(value)}
                </span>
              </div>
              <ul className="flex flex-col gap-0.5">
                {rows.map((c) => {
                  const d = DIRECTION[c.direction] ?? DIRECTION.mixed;
                  const isSel = selected === c.code;
                  // Two lines so the name never gets squeezed in a narrow column:
                  // name · share and R$ / bar · direction in words. The right column has a fixed
                  // width, so every bar track has the same length (one scale for all causes).
                  const content = (
                    <>
                      <span className="block min-w-0 break-words text-[13px] font-semibold leading-snug text-ink">
                        {c.label}
                      </span>
                      <span className="block text-right text-[13px] font-semibold leading-snug text-ink tabular">
                        {pct(c.share, 0)} · {money(c.abs_error)}
                      </span>
                      <span
                        aria-hidden
                        className="relative block h-2.5 min-w-[120px] rounded-[3px] bg-[#f3f5fc]"
                      >
                        <span
                          className={clsx("absolute inset-y-0 left-0 rounded-[3px]", style.className)}
                          style={{ width: `${Math.max(1, (c.share / maxShare) * 100)}%` }}
                        />
                      </span>
                      <span className="flex items-center justify-end gap-1 text-right text-[11.5px] leading-snug text-muted">
                        <d.Icon aria-hidden size={12} strokeWidth={2.5} style={{ color: d.color }} />
                        {d.text}
                      </span>
                    </>
                  );
                  const grid =
                    "grid w-full grid-cols-[minmax(0,1fr)_10.5rem] items-center gap-x-4 gap-y-1 rounded-xl px-3 py-1.5 text-left";
                  return (
                    <li key={c.code}>
                      {onSelect ? (
                        <button
                          type="button"
                          aria-pressed={isSel}
                          onClick={() => onSelect(c.code)}
                          className={clsx(
                            grid,
                            "transition hover:bg-[#f4f7ff] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/60",
                            isSel && clsx("bg-[#eaf2ff]", FOCUS_RING),
                          )}
                        >
                          {content}
                        </button>
                      ) : (
                        <div className={grid}>{content}</div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}
      </div>
    </ChartFrame>
  );
}
