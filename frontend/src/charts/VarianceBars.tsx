/**
 * "Onde está o desvio?" (spec §2.3.4) and the report chapter "Gap" (§2.2.2): an HTML bar list.
 *
 * plan mode  · diverging Δ bars on a shared scale (adverse first, then favourable), the signed Δ
 *              with "acima/abaixo", Δ%, ≤ 2 tag chips, the chance of reaching the reference
 *              (fc_*) and a Pareto marker "{cum} acum." on adverse rows; a dashed line closes the
 *              "vital few" (cumulative adverse share ≥ 50%).
 * error mode · absolute error split into the systematic part (solid, colour = net direction) and
 *              the noise that cancels out (light), with "WMAPE {w}" and the bias badge.
 *
 * Each row is a `button` with `aria-pressed` (click = focus/select). The "›" button, a double
 * click or Shift+Enter drills down (`onDrill`), disabled when the member is not drillable.
 * Names wrap; nothing is cut off. At most 12 rows, then "Demais (n)".
 */
import clsx from "clsx";
import { ChevronRight } from "lucide-react";
import type { KeyboardEvent, ReactNode } from "react";

import { BiasBadge, ChartFrame } from "../components/ui";
import { money, pct, type Measure } from "../lib/format";
import {
  FOCUS_RING,
  IBCS,
  MAX_CATEGORIES,
  capCategories,
  deltaColor,
  errorColor,
  errorWord,
  probColor,
  varianceText,
} from "../lib/ibcs";
import type { ErrorRow, PlanRow } from "../types/deviations";

export interface VarianceBarsProps {
  rows: PlanRow[] | ErrorRow[];
  mode: "plan" | "error";
  measure: Measure;
  others?: { n: number; value: number } | null;
  selectedKey?: string;
  onSelect?: (key: string) => void;
  onDrill?: (key: string) => void;
  ariaLabel: string;
}

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Folds rows beyond the 12th into "Demais", adding them to the backend's own `others`. */
function fold<T>(rows: T[], others: VarianceBarsProps["others"], value: (r: T) => number) {
  const { shown, rest } = capCategories(rows, MAX_CATEGORIES);
  if (!rest.length) return { shown, others: others ?? null };
  return {
    shown,
    others: {
      n: (others?.n ?? 0) + rest.length,
      value: (others?.value ?? 0) + rest.reduce((s, r) => s + value(r), 0),
    },
  };
}

export function VarianceBars(props: VarianceBarsProps) {
  return props.mode === "error" ? <ErrorBars {...props} /> : <PlanBars {...props} />;
}

/* ------------------------------------------------------------------ shared */

/**
 * One row: name | bar | value on the first line; chips (tags, chance, Pareto, WMAPE, bias) on a
 * second line spanning the name and bar columns, so long chips wrap instead of running over the
 * bar. The value block spans both lines.
 */
function RowShell({
  rowKey,
  label,
  selected,
  drillable,
  onSelect,
  onDrill,
  bar,
  value,
  meta,
}: {
  rowKey: string;
  label: string;
  selected: boolean;
  drillable: boolean;
  onSelect?: (key: string) => void;
  onDrill?: (key: string) => void;
  bar: ReactNode;
  value: ReactNode;
  meta?: ReactNode;
}) {
  const canDrill = drillable && !!onDrill;
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "Enter" && e.shiftKey && canDrill) {
      e.preventDefault();
      onDrill!(rowKey);
    }
  };
  return (
    <li className="flex items-stretch gap-1.5">
      <button
        type="button"
        aria-pressed={selected}
        onClick={() => onSelect?.(rowKey)}
        onDoubleClick={() => canDrill && onDrill!(rowKey)}
        onKeyDown={onKeyDown}
        className={clsx(
          // Fixed value column: every row gets the same bar track, so all bars share one scale.
          "grid min-w-0 flex-1 grid-cols-[minmax(0,1.15fr)_minmax(120px,1fr)_9.75rem] items-center gap-x-4 gap-y-1 rounded-xl px-3 py-2 text-left transition",
          "hover:bg-[#f4f7ff] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/60",
          selected && clsx("bg-[#eaf2ff]", FOCUS_RING),
          !onSelect && "cursor-default",
        )}
      >
        <span className="col-start-1 row-start-1 block min-w-0 break-words text-[13px] font-semibold leading-snug text-ink">
          {label}
        </span>
        <span aria-hidden className="col-start-2 row-start-1 block min-w-[120px]">
          {bar}
        </span>
        <span className={clsx("col-start-3 row-start-1 block text-right tabular", meta && "row-span-2")}>
          {value}
        </span>
        {meta && (
          <span className="col-span-2 col-start-1 row-start-2 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            {meta}
          </span>
        )}
      </button>
      {onDrill && (
        <button
          type="button"
          aria-label={`Detalhar ${label}`}
          title={drillable ? `Detalhar ${label}` : "Sem nível abaixo para detalhar"}
          disabled={!drillable}
          onClick={() => onDrill(rowKey)}
          className="flex w-8 shrink-0 items-center justify-center rounded-xl text-ink-2 transition hover:bg-[#eef1fa] hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-30"
        >
          <ChevronRight size={16} aria-hidden />
        </button>
      )}
    </li>
  );
}

/** Tag chip that wraps (unlike `Badge`, which never breaks): long backend tags stay inside the row. */
function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="inline-block max-w-full break-words rounded-full bg-[#eef1fa] px-2.5 py-0.5 text-[11px] font-semibold leading-snug text-ink-2">
      {children}
    </span>
  );
}

function Hint({ onSelect, onDrill }: Pick<VarianceBarsProps, "onSelect" | "onDrill">) {
  if (!onSelect && !onDrill) return null;
  return (
    <span className="text-muted">
      {[onSelect && "Clique para focar", onDrill && "›  para detalhar"].filter(Boolean).join(" · ")}
    </span>
  );
}

function OthersRow({ n, text }: { n: number; text: string }) {
  return (
    <li className="flex items-center justify-between gap-4 px-3 py-2 text-[12.5px] text-muted">
      <span>Demais ({n.toLocaleString("pt-BR")})</span>
      <span className="tabular text-right">{text}</span>
    </li>
  );
}

/* -------------------------------------------------------------------- plan */

function PlanBars({ rows, measure, others, selectedKey, onSelect, onDrill, ariaLabel }: VarianceBarsProps) {
  const folded = fold(rows as PlanRow[], others, (r) => r.variance);
  const shown = folded.shown;
  const maxNeg = Math.max(0, ...shown.map((r) => -r.variance));
  const maxPos = Math.max(0, ...shown.map((r) => r.variance));
  const total = maxNeg + maxPos || 1;
  const zero = (maxNeg / total) * 100; // zero line position (%), shared scale on both sides
  // The "vital few": first adverse row whose cumulative share reaches 50%.
  const cutIndex = shown.findIndex((r) => r.variance < 0 && isNum(r.cum_share) && r.cum_share >= 0.5);
  const hasProb = shown.some((r) => isNum(r.prob_hit));

  const pctText = (r: PlanRow) => (isNum(r.variance_pct) ? pct(r.variance_pct, 1, true) : "—");
  const noRef = (r: PlanRow) =>
    !isNum(r.variance_pct) && r.p === 0 && !r.tags.some((t) => /sem.or[cç]amento/i.test(t.label));

  return (
    <ChartFrame
      ariaLabel={ariaLabel}
      columns={[
        { label: "Membro" },
        { label: "Desvio", align: "right" },
        { label: "Desvio %", align: "right" },
        ...(hasProb ? [{ label: "Chance de atingir", align: "right" as const }] : []),
        { label: "Acumulado das perdas", align: "right" },
      ]}
      rows={[
        ...shown.map((r) => ({
          key: r.key,
          cells: [
            r.label,
            varianceText(r.variance, measure),
            pctText(r),
            ...(hasProb ? [pct(r.prob_hit, 0)] : []),
            r.variance < 0 && isNum(r.cum_share) ? pct(r.cum_share, 0) : "—",
          ],
        })),
        ...(folded.others
          ? [
              {
                key: "__demais__",
                cells: [
                  `Demais (${folded.others.n.toLocaleString("pt-BR")})`,
                  varianceText(folded.others.value, measure),
                  "—",
                  ...(hasProb ? ["—"] : []),
                  "—",
                ],
              },
            ]
          : []),
      ]}
      legend={
        <>
          <span className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-2.5 w-4 rounded-sm"
              style={{ background: IBCS.bad }}
            />
            abaixo
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-2.5 w-4 rounded-sm"
              style={{ background: IBCS.good }}
            />
            acima
          </span>
          <Hint onSelect={onSelect} onDrill={onDrill} />
        </>
      }
    >
      <ul aria-label={ariaLabel} className="flex flex-col gap-0.5">
        {shown.map((r, i) => {
          const width = (Math.abs(r.variance) / total) * 100;
          const left = r.variance < 0 ? zero - width : zero;
          const tags = r.tags.slice(0, 2);
          const meta =
            tags.length || noRef(r) || isNum(r.prob_hit) || (r.variance < 0 && isNum(r.cum_share)) ? (
              <>
                {tags.map((t) => (
                  <Chip key={t.code}>{t.label}</Chip>
                ))}
                {noRef(r) && <Chip>Sem orçamento</Chip>}
                {isNum(r.prob_hit) && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-ink-2">
                    <span
                      aria-hidden
                      className="inline-block h-2 w-2 rounded-full"
                      style={{ background: probColor(r.prob_hit) }}
                    />
                    {pct(r.prob_hit, 0)} de chance
                  </span>
                )}
                {r.variance < 0 && isNum(r.cum_share) && (
                  <span className="text-[11px] font-medium text-muted">{pct(r.cum_share, 0)} acum.</span>
                )}
              </>
            ) : null;
          return [
            <RowShell
              key={r.key}
              rowKey={r.key}
              label={r.label}
              selected={selectedKey === r.key}
              drillable={r.drillable}
              onSelect={onSelect}
              onDrill={onDrill}
              meta={meta}
              bar={
                <span className="relative block h-4">
                  <span className="absolute inset-y-0 w-px bg-[#c3c8d9]" style={{ left: `${zero}%` }} />
                  <span
                    className="absolute inset-y-0.5 rounded-[3px]"
                    style={{
                      left: `${left}%`,
                      width: `${Math.max(width, r.variance === 0 ? 0 : 0.8)}%`,
                      background: deltaColor(r.variance),
                    }}
                  />
                </span>
              }
              value={
                <>
                  <span
                    className="block text-[13px] font-semibold leading-snug"
                    style={{ color: r.variance < 0 ? "#b42323" : "#0b7a0b" }}
                  >
                    {varianceText(r.variance, measure)}
                  </span>
                  <span className="block text-[11.5px] text-muted">{pctText(r)}</span>
                </>
              }
            />,
            i === cutIndex && i < shown.length - 1 ? (
              <li
                key={`${r.key}__cut`}
                aria-hidden
                className="flex items-center gap-2 px-3 py-0.5 text-[10.5px] font-medium text-muted"
              >
                <span className="h-0 flex-1 border-t border-dashed border-[#a3a8bf]" />
                {i === 0 ? "este membro concentra" : `estes ${i + 1} concentram`} metade das perdas
                <span className="h-0 flex-1 border-t border-dashed border-[#a3a8bf]" />
              </li>
            ) : null,
          ];
        })}
        {folded.others && <OthersRow n={folded.others.n} text={varianceText(folded.others.value, measure)} />}
      </ul>
    </ChartFrame>
  );
}

/* ------------------------------------------------------------------- error */

function ErrorBars({ rows, others, selectedKey, onSelect, onDrill, ariaLabel }: VarianceBarsProps) {
  const folded = fold(rows as ErrorRow[], others, (r) => r.abs_error);
  const shown = folded.shown;
  const max = Math.max(0, ...shown.map((r) => r.abs_error)) || 1;
  const dirText = (r: ErrorRow) => (r.net_error === 0 ? "sem viés líquido" : errorWord(r.net_error));

  return (
    <ChartFrame
      ariaLabel={ariaLabel}
      columns={[
        { label: "Membro" },
        { label: "Erro (R$)", align: "right" },
        { label: "Sistemático", align: "right" },
        { label: "Ruído", align: "right" },
        { label: "Participação", align: "right" },
        { label: "WMAPE", align: "right" },
        { label: "Viés", align: "right" },
      ]}
      rows={[
        ...shown.map((r) => ({
          key: r.key,
          cells: [
            r.label,
            money(r.abs_error),
            `${money(r.systematic)} (${dirText(r)})`,
            money(r.noise),
            pct(r.share, 0),
            pct(r.wmape),
            pct(r.bias, 1, true),
          ],
        })),
        ...(folded.others
          ? [
              {
                key: "__demais__",
                cells: [
                  `Demais (${folded.others.n.toLocaleString("pt-BR")})`,
                  money(folded.others.value),
                  "—",
                  "—",
                  "—",
                  "—",
                  "—",
                ],
              },
            ]
          : []),
      ]}
      legend={
        <>
          <span className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-2.5 w-4 rounded-sm"
              style={{ background: IBCS.over }}
            />
            superestimou
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-2.5 w-4 rounded-sm"
              style={{ background: IBCS.under }}
            />
            subestimou
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden className="inline-flex h-2.5 w-5 overflow-hidden rounded-sm">
              <span className="w-1/2" style={{ background: IBCS.ink2 }} />
              <span className="w-1/2" style={{ background: IBCS.ink2, opacity: 0.28 }} />
            </span>
            sólido = viés sistemático · claro = ruído que se compensa
          </span>
          <Hint onSelect={onSelect} onDrill={onDrill} />
        </>
      }
    >
      <ul aria-label={ariaLabel} className="flex flex-col gap-0.5">
        {shown.map((r) => {
          const color = errorColor(r.net_error);
          const sys = (r.systematic / max) * 100;
          const noise = (Math.max(0, r.noise) / max) * 100;
          return (
            <RowShell
              key={r.key}
              rowKey={r.key}
              label={r.label}
              selected={selectedKey === r.key}
              drillable={r.drillable}
              onSelect={onSelect}
              onDrill={onDrill}
              meta={
                <>
                  <Chip>WMAPE {pct(r.wmape)}</Chip>
                  {r.bias_class && <BiasBadge value={r.bias_class} />}
                </>
              }
              bar={
                <span className="flex h-4 items-stretch">
                  <span className="rounded-l-[3px]" style={{ width: `${sys}%`, background: color }} />
                  <span
                    className="rounded-r-[3px]"
                    style={{ width: `${noise}%`, background: color, opacity: 0.28 }}
                  />
                </span>
              }
              value={
                <>
                  <span className="block text-[13px] font-semibold leading-snug text-ink">
                    {money(r.abs_error)}
                  </span>
                  <span className="block text-[11.5px] text-muted">
                    {pct(r.share, 0)} do erro · {dirText(r)}
                  </span>
                </>
              }
            />
          );
        })}
        {folded.others && <OthersRow n={folded.others.n} text={money(folded.others.value)} />}
      </ul>
    </ChartFrame>
  );
}
