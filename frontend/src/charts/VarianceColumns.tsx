/**
 * IBCS monthly variance chart (spec §2.2.2 "monthly_variance", §2.3.4 "Quando aconteceu?").
 *
 * plan mode  · top grid: the compared value X (AC solid or FC hatched) in front of the reference
 *              P (PL outline, TG dashed outline or PY gray), plus a dashed Meta tick when targets
 *              exist; bottom grid: Δ = X − P bars, green above / red below, signed labels.
 *              Quarters (fc_*) appear as labelled bands with their Δ.
 * error mode · top grid: Real (AC solid) in front of the forecast (FC hatched); bottom grid: the
 *              signed error (forecast − actual), red = superestimou, blue = subestimou.
 *
 * No legend box (a scenario key names the notations), no value axis, no gridlines.
 * Clicking a month calls `onSelectMonth("YYYY-MM")`; the selected month stays at full opacity.
 */
import { useMemo } from "react";

import { ChartFrame } from "../components/ui";
import { fmtMeasure, monthLabel, pct, shortMonth, signedMeasure, type Measure } from "../lib/format";
import {
  IBCS,
  NOTATION_SWATCH,
  deltaColor,
  errorColor,
  errorWord,
  escapeHtml,
  notationItemStyle,
  shortSigned,
  useElementWidth,
  varianceText,
  type Notation,
} from "../lib/ibcs";
import type { MonthlyErrorRow, MonthlyPlanRow } from "../types/deviations";
import { EChart, TOOLTIP_STYLE, type EChartsOption } from "./EChart";

export interface VarianceColumnsProps {
  rows: MonthlyPlanRow[] | MonthlyErrorRow[];
  mode: "plan" | "error";
  /** Notation of the compared side in plan mode (AC for ac_pl, FC for fc_*). Default FC. */
  xKind?: "AC" | "FC";
  /** Plan: name of the compared side ("Consenso", "Real"). Error: name of the forecast ("Estatístico"). */
  xLabel: string;
  /** Plan: name of the reference ("Orçamento", "Meta", "Ano anterior"). */
  pLabel?: string;
  /** Notation of the reference; derived from `pLabel` when omitted. */
  pKind?: "PL" | "TG" | "PY";
  measure: Measure;
  quarters?: { label: string; start: string; end: string; variance: number }[] | null;
  /** Highlighted month: "YYYY-MM" (the URL `periodo`) or an ISO date; only the month is compared. */
  selectedMonth?: string;
  /** Called with the clicked month as "YYYY-MM", ready for `periodo` (spec §2.3.5). */
  onSelectMonth?: (month: string) => void;
  height?: number;
  ariaLabel: string;
}

/** "2026-10-01" → "2026-10" (also accepts "2026-10"). */
const monthKey = (d: string) => d.slice(0, 7);

const pKindOf = (label?: string): "PL" | "TG" | "PY" => {
  const l = (label ?? "").toLowerCase();
  if (l.startsWith("meta")) return "TG";
  if (l.startsWith("ano anterior")) return "PY";
  return "PL";
};

/** Dashed horizontal tick (TG marker). */
const TICK_SYMBOL = "path://M0,0 H5 V2 H0 Z M8,0 H13 V2 H8 Z M16,0 H21 V2 H16 Z M24,0 H29 V2 H24 Z";

interface Point {
  date: string;
  /** Front column (plan: X; error: actual). */
  front: number | null;
  /** Back column (plan: P; error: forecast). */
  back: number | null;
  /** Bottom strip (plan: X − P; error: forecast − actual). */
  delta: number | null;
  deltaPct: number | null;
  target: number | null;
}

function toPoints(rows: VarianceColumnsProps["rows"], mode: "plan" | "error"): Point[] {
  if (mode === "error") {
    return (rows as MonthlyErrorRow[]).map((r) => ({
      date: r.date,
      front: r.actual,
      back: r.forecast,
      delta: r.error ?? r.forecast - r.actual,
      deltaPct: r.wmape,
      target: null,
    }));
  }
  return (rows as MonthlyPlanRow[]).map((r) => ({
    date: r.date,
    front: r.x,
    back: r.p,
    delta: r.variance ?? (r.x != null && r.p != null ? r.x - r.p : null),
    deltaPct: r.variance_pct,
    target: r.target,
  }));
}

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function VarianceColumns({
  rows,
  mode,
  xKind = "FC",
  xLabel,
  pLabel,
  pKind,
  measure,
  quarters,
  selectedMonth,
  onSelectMonth,
  height = 300,
  ariaLabel,
}: VarianceColumnsProps) {
  const { ref, width } = useElementWidth<HTMLDivElement>();
  const points = useMemo(() => toPoints(rows, mode), [rows, mode]);
  const isError = mode === "error";
  // Error mode always shows Real vs the forecast, whatever the caller called them.
  const frontLabel = isError ? "Real" : xLabel;
  const backLabel = isError
    ? xLabel && xLabel.toLowerCase() !== "real"
      ? xLabel
      : (pLabel ?? "Previsto")
    : (pLabel ?? "Orçamento");
  const frontKind: Notation = isError ? "AC" : xKind;
  const backKind: Notation = isError ? "FC" : (pKind ?? pKindOf(pLabel));
  const showTarget = !isError && backKind !== "TG" && points.some((p) => isNum(p.target));
  const deltaLabel = isError ? `Erro (${backLabel} − Real)` : `Δ ${frontLabel} − ${backLabel}`;

  const option = useMemo<EChartsOption>(() => {
    const n = Math.max(1, points.length);
    const catW = Math.max(24, ((width || 640) - 16) / n);
    const barPx = Math.max(6, Math.min(34, catW * 0.42));
    const sel = selectedMonth ? monthKey(selectedMonth) : null;
    const dim = (i: number) => (!sel || (points[i] && monthKey(points[i].date) === sel) ? 1 : 0.3);
    // Δ labels only when they fit; the top grid stays unlabelled (values are in the tooltip and
    // the table), so labels never collide with the reference outline or the Meta tick.
    const labelsOn = n <= 12 && catW >= 40;

    const topH = Math.round((height - 34 - 30) * 0.56);
    const bottomTop = 34 + topH + 18;
    const values = points.flatMap((p) => [p.front, p.back, showTarget ? p.target : null]).filter(isNum);
    const topMax = values.length ? Math.max(...values, 0) * 1.06 : 1;
    const deltas = points.map((p) => p.delta).filter(isNum);
    const maxAbs = deltas.length ? Math.max(...deltas.map(Math.abs)) || 1 : 1;
    const hasNeg = deltas.some((d) => d < 0);
    const hasPos = deltas.some((d) => d > 0);
    const dColor = (d: number) => (isError ? errorColor(d) : deltaColor(d));

    const dates = points.map((p) => p.date);
    const qAreas = (quarters ?? [])
      .filter((q) => dates.includes(q.start) && dates.includes(q.end))
      .map((q, k) => [
        {
          xAxis: q.start,
          name: `${q.label.split(" · ")[0]} · ${signedMeasure(q.variance, measure)}`,
          itemStyle: { color: k % 2 === 0 ? "rgba(27,31,59,0.035)" : "rgba(0,0,0,0)" },
          label: { color: deltaColor(q.variance) },
        },
        { xAxis: q.end },
      ]);

    return {
      animationDuration: 400,
      grid: [
        { left: 8, right: 8, top: 34, height: topH },
        { left: 8, right: 8, top: bottomTop, bottom: 30 },
      ],
      tooltip: {
        ...TOOLTIP_STYLE,
        trigger: "item",
        formatter: (p: { dataIndex: number }) => {
          const pt = points[p.dataIndex];
          if (!pt) return "";
          const lines = [
            `<b>${escapeHtml(monthLabel(pt.date))}</b>`,
            `${escapeHtml(frontLabel)}: ${fmtMeasure(pt.front, measure)}`,
            `${escapeHtml(backLabel)}: ${fmtMeasure(pt.back, measure)}`,
          ];
          if (showTarget && isNum(pt.target)) lines.push(`Meta: ${fmtMeasure(pt.target, measure)}`);
          if (isNum(pt.delta)) {
            lines.push(
              isError
                ? `Erro: ${signedMeasure(pt.delta, measure)} (${errorWord(pt.delta)})` +
                    (isNum(pt.deltaPct) ? ` · WMAPE ${pct(pt.deltaPct)}` : "")
                : `Δ: ${varianceText(pt.delta, measure)}` +
                    (isNum(pt.deltaPct) ? ` (${pct(pt.deltaPct, 1, true)})` : ""),
            );
          }
          return lines.join("<br/>");
        },
      },
      xAxis: [
        {
          type: "category",
          gridIndex: 0,
          data: dates,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { show: false },
          splitLine: { show: false },
        },
        {
          type: "category",
          gridIndex: 1,
          data: dates,
          position: "bottom",
          axisLine: { onZero: true, lineStyle: { color: IBCS.axis } },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: {
            interval: 0,
            color: IBCS.ink2,
            fontSize: 11,
            margin: 10,
            width: Math.max(28, catW - 2),
            overflow: "break",
            formatter: (v: string) => shortMonth(v),
          },
        },
      ],
      yAxis: [
        { type: "value", gridIndex: 0, show: false, min: 0, max: topMax, splitLine: { show: false } },
        {
          type: "value",
          gridIndex: 1,
          show: false,
          min: hasNeg ? -maxAbs * 1.45 : 0,
          max: hasPos ? maxAbs * 1.45 : 0,
          splitLine: { show: false },
        },
      ],
      series: [
        {
          id: "back",
          name: backLabel,
          type: "bar",
          xAxisIndex: 0,
          yAxisIndex: 0,
          barWidth: barPx,
          barGap: "-62%",
          z: 2,
          emphasis: { disabled: true },
          data: points.map((p, i) => ({ value: p.back, itemStyle: notationItemStyle(backKind, dim(i)) })),
        },
        {
          id: "front",
          name: frontLabel,
          type: "bar",
          xAxisIndex: 0,
          yAxisIndex: 0,
          barWidth: barPx,
          z: 3,
          emphasis: { disabled: true },
          data: points.map((p, i) => ({ value: p.front, itemStyle: notationItemStyle(frontKind, dim(i)) })),
          markArea: qAreas.length
            ? {
                silent: true,
                label: { show: true, position: "top", distance: 6, fontSize: 11, fontWeight: 600 },
                data: qAreas,
              }
            : undefined,
        },
        ...(showTarget
          ? [
              {
                id: "target",
                name: "Meta",
                type: "scatter",
                xAxisIndex: 0,
                yAxisIndex: 0,
                z: 4,
                symbol: TICK_SYMBOL,
                symbolSize: [barPx * 1.9, 2.5],
                itemStyle: { color: IBCS.ink },
                data: points.map((p, i) => ({
                  value: isNum(p.target) ? p.target : null,
                  itemStyle: { opacity: dim(i) },
                })),
              },
            ]
          : []),
        {
          id: "delta",
          name: deltaLabel,
          type: "bar",
          xAxisIndex: 1,
          yAxisIndex: 1,
          barWidth: barPx,
          emphasis: { disabled: true },
          data: points.map((p, i) => {
            const d = p.delta;
            return {
              value: d,
              itemStyle: { color: isNum(d) ? dColor(d) : IBCS.neutral, opacity: dim(i) },
              label: {
                show: labelsOn && isNum(d),
                position: isNum(d) && d < 0 ? "bottom" : "top",
                distance: 4,
                formatter: isNum(d) ? shortSigned(d) : "",
                color: isNum(d) ? dColor(d) : IBCS.muted,
                fontSize: 10,
                fontWeight: 700,
                opacity: dim(i),
              },
            };
          }),
        },
      ],
    };
  }, [
    points,
    width,
    height,
    selectedMonth,
    quarters,
    measure,
    isError,
    frontLabel,
    backLabel,
    frontKind,
    backKind,
    showTarget,
    deltaLabel,
  ]);

  const columns = isError
    ? [
        { label: "Mês" },
        { label: "Real", align: "right" as const },
        { label: backLabel, align: "right" as const },
        { label: "Erro", align: "right" as const },
        { label: "WMAPE", align: "right" as const },
      ]
    : [
        { label: "Mês" },
        { label: frontLabel, align: "right" as const },
        { label: backLabel, align: "right" as const },
        { label: "Desvio", align: "right" as const },
        { label: "Desvio %", align: "right" as const },
      ];
  // In the table, months stay selectable from the keyboard.
  const monthCell = (d: string) =>
    onSelectMonth ? (
      <button
        type="button"
        aria-pressed={!!selectedMonth && monthKey(selectedMonth) === monthKey(d)}
        onClick={() => onSelectMonth(monthKey(d))}
        className="font-semibold text-brand-dark underline-offset-2 hover:underline"
      >
        {monthLabel(d)}
      </button>
    ) : (
      monthLabel(d)
    );
  const tableRows = points.map((p) => ({
    key: p.date,
    cells: isError
      ? [
          monthCell(p.date),
          fmtMeasure(p.front, measure),
          fmtMeasure(p.back, measure),
          isNum(p.delta) ? `${signedMeasure(p.delta, measure)} (${errorWord(p.delta)})` : "—",
          pct(p.deltaPct),
        ]
      : [
          monthCell(p.date),
          fmtMeasure(p.front, measure),
          fmtMeasure(p.back, measure),
          isNum(p.delta) ? varianceText(p.delta, measure) : "—",
          pct(p.deltaPct, 1, true),
        ],
  }));

  return (
    <ChartFrame
      ariaLabel={ariaLabel}
      columns={columns}
      rows={tableRows}
      legend={
        <>
          <Key kind={frontKind} label={frontLabel} />
          <Key kind={backKind} label={backLabel} />
          {showTarget && (
            <span className="inline-flex items-center gap-1.5">
              <span aria-hidden className="inline-block w-4 border-t-[2px] border-dashed border-[#1b1f3b]" />
              Meta
            </span>
          )}
          <span className="text-muted">
            {isError
              ? "Erro: vermelho = superestimou · azul = subestimou"
              : `Δ vs ${backLabel.toLowerCase()}: verde = acima · vermelho = abaixo`}
          </span>
          {onSelectMonth && <span className="text-muted">Clique em um mês para filtrar</span>}
        </>
      }
    >
      <div ref={ref}>
        <EChart
          option={option}
          height={height}
          ariaLabel={ariaLabel}
          onClick={(p) => {
            const pt = points[p.dataIndex];
            if (pt && onSelectMonth) onSelectMonth(monthKey(pt.date));
          }}
        />
      </div>
    </ChartFrame>
  );
}

function Key({ kind, label }: { kind: Notation; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden className={`inline-block h-3 w-3 rounded-[3px] ${NOTATION_SWATCH[kind]}`} />
      {label}
    </span>
  );
}
