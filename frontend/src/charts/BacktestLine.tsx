/**
 * Out-of-sample backtest in R$ (spec §2.1, step 3): Real (solid ink, 2.4 px) vs the champion
 * statistical forecast (blue dashed) vs the naive method (gray dotted).
 * Direct end labels instead of a legend; no gridlines; compact value axis without lines.
 */
import { useMemo } from "react";

import { ChartFrame } from "../components/ui";
import { money, monthLabel, pct, shortMonth } from "../lib/format";
import { IBCS, escapeHtml, shortNumber } from "../lib/ibcs";
import { EChart, TOOLTIP_STYLE, type EChartsOption } from "./EChart";

export interface BacktestLineRow {
  date: string;
  actual: number;
  statistical: number;
  naive: number;
}

export interface BacktestLineProps {
  rows: BacktestLineRow[];
  height?: number;
  ariaLabel: string;
}

const LINES = [
  { key: "actual", name: "Real", color: IBCS.ink, type: "solid", width: 2.4 },
  { key: "statistical", name: "Estatístico", color: "#2a78d6", type: "dashed", width: 2 },
  { key: "naive", name: "Ingênuo", color: "#9aa0b8", type: "dotted", width: 2 },
] as const;

/** Absolute percentage error of a month (null without actuals). */
const ape = (f: number, a: number) => (a ? Math.abs(f - a) / Math.abs(a) : null);

export function BacktestLine({ rows, height = 260, ariaLabel }: BacktestLineProps) {
  const option = useMemo<EChartsOption>(
    () => ({
      animationDuration: 500,
      grid: { left: 8, right: 96, top: 18, bottom: 6, containLabel: true },
      tooltip: {
        ...TOOLTIP_STYLE,
        trigger: "axis",
        axisPointer: { type: "line", lineStyle: { color: IBCS.axis } },
        formatter: (ps: { dataIndex: number }[]) => {
          const r = rows[ps[0]?.dataIndex ?? -1];
          if (!r) return "";
          return [
            `<b>${escapeHtml(monthLabel(r.date))}</b>`,
            `Real: ${money(r.actual)}`,
            `Estatístico: ${money(r.statistical)} (erro ${pct(ape(r.statistical, r.actual))})`,
            `Ingênuo: ${money(r.naive)} (erro ${pct(ape(r.naive, r.actual))})`,
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: rows.map((r) => r.date),
        axisTick: { show: false },
        axisLine: { lineStyle: { color: IBCS.axis } },
        splitLine: { show: false },
        axisLabel: {
          color: IBCS.ink2,
          fontSize: 11,
          margin: 10,
          hideOverlap: true,
          formatter: (v: string) => shortMonth(v),
        },
      },
      yAxis: {
        type: "value",
        scale: true,
        splitLine: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: IBCS.muted, fontSize: 10.5, formatter: (v: number) => shortNumber(v) },
      },
      series: LINES.map((l) => ({
        id: l.key,
        name: l.name,
        type: "line",
        symbol: "none",
        smooth: false,
        z: l.key === "actual" ? 3 : 2,
        lineStyle: { color: l.color, width: l.width, type: l.type },
        itemStyle: { color: l.color },
        emphasis: { disabled: true },
        endLabel: {
          show: true,
          formatter: l.name,
          color: l.color === IBCS.ink ? IBCS.ink : l.color,
          fontSize: 11.5,
          fontWeight: 600,
          distance: 8,
          // Vertical padding gives shiftY room: the three lines often end within a few pixels.
          padding: [4, 0],
        },
        labelLayout: { moveOverlap: "shiftY" },
        data: rows.map((r) => r[l.key]),
      })),
    }),
    [rows],
  );

  return (
    <ChartFrame
      ariaLabel={ariaLabel}
      columns={[
        { label: "Mês" },
        { label: "Real", align: "right" },
        { label: "Estatístico", align: "right" },
        { label: "Ingênuo", align: "right" },
      ]}
      rows={rows.map((r) => ({
        key: r.date,
        cells: [monthLabel(r.date), money(r.actual), money(r.statistical), money(r.naive)],
      }))}
    >
      <EChart option={option} height={height} ariaLabel={ariaLabel} />
    </ChartFrame>
  );
}
