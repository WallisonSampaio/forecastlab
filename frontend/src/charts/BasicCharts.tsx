import { useMemo } from "react";

import { CATEGORICAL, DIVERGING, SEQ_BLUE, SERIES, STATUS } from "../lib/colors";
import { compact, formatValue, pct } from "../lib/format";
import { AXIS_STYLE, EChart, TOOLTIP_STYLE, type EChartsOption } from "./EChart";

const axisFmt = (format?: string) => (v: number) =>
  format === "percent" || format === "percent_signed"
    ? pct(v, 0)
    : format === "currency"
      ? `R$${compact(v)}`
      : compact(v);

export interface BarSeries {
  name: string;
  data: (number | null)[];
  color?: string;
  dashed?: boolean;
}

interface BarProps {
  categories: string[];
  series: BarSeries[];
  format?: string;
  horizontal?: boolean;
  height?: number;
  stacked?: boolean;
  /** Color each bar by sign (diverging: positive red, negative blue) e.g. bias. */
  signColors?: { positive: string; negative: string };
  highlight?: number;
  onClick?: (name: string) => void;
}

export function BarChart({
  categories,
  series,
  format,
  horizontal = false,
  height = 300,
  stacked = false,
  signColors,
  highlight,
  onClick,
}: BarProps) {
  const option = useMemo<EChartsOption>(() => {
    const cat = {
      type: "category",
      data: categories,
      ...AXIS_STYLE,
      axisLabel: {
        ...AXIS_STYLE.axisLabel,
        width: horizontal ? 150 : 90,
        overflow: "truncate",
        interval: 0,
        rotate: !horizontal && categories.length > 8 ? 30 : 0,
      },
      inverse: horizontal,
    };
    const val = {
      type: "value",
      ...AXIS_STYLE,
      axisLine: { show: false },
      axisLabel: { ...AXIS_STYLE.axisLabel, formatter: axisFmt(format) },
    };
    return {
      grid: {
        left: horizontal ? 160 : 56,
        right: 32,
        top: series.length > 1 ? 36 : 16,
        bottom: horizontal ? 24 : 48,
      },
      legend:
        series.length > 1 ? { top: 0, left: 0, icon: "roundRect", itemWidth: 14, itemHeight: 8 } : undefined,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        ...TOOLTIP_STYLE,
        valueFormatter: (v: number) => formatValue(v, format),
      },
      xAxis: horizontal ? val : cat,
      yAxis: horizontal ? cat : val,
      series: series.map((s, i) => ({
        name: s.name,
        type: "bar",
        stack: stacked ? "s" : undefined,
        barMaxWidth: 28,
        barGap: "10%",
        data: s.data.map((v, j) => ({
          value: v,
          itemStyle: {
            color: signColors
              ? (v ?? 0) >= 0
                ? signColors.positive
                : signColors.negative
              : highlight !== undefined && j !== highlight && series.length === 1
                ? "#cbd5e1"
                : (s.color ?? CATEGORICAL[i % CATEGORICAL.length]),
            borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0],
          },
        })),
      })),
    } as EChartsOption;
  }, [categories, series, format, horizontal, stacked, signColors, highlight]);
  return <EChart option={option} height={height} onClick={onClick ? (p) => onClick(p.name) : undefined} />;
}

interface WaterfallProps {
  labels: string[];
  values: number[];
  kinds: string[]; // "total" | "delta"
  format?: string;
  height?: number;
}

export function WaterfallChart({ labels, values, kinds, format, height = 300 }: WaterfallProps) {
  const option = useMemo<EChartsOption>(() => {
    const base: (number | string)[] = [];
    const pos: (number | string)[] = [];
    const neg: (number | string)[] = [];
    const tot: (number | string)[] = [];
    let running = 0;
    values.forEach((v, i) => {
      if (kinds[i] === "total") {
        running = v;
        base.push("-");
        pos.push("-");
        neg.push("-");
        tot.push(v);
      } else if (v >= 0) {
        base.push(running);
        pos.push(v);
        neg.push("-");
        tot.push("-");
        running += v;
      } else {
        running += v;
        base.push(running);
        pos.push("-");
        neg.push(-v);
        tot.push("-");
      }
    });
    return {
      grid: { left: 64, right: 24, top: 16, bottom: 56 },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        ...TOOLTIP_STYLE,
        formatter: (ps: { dataIndex: number }[]) => {
          const i = ps[0].dataIndex;
          return `<b>${labels[i]}</b><br/>${formatValue(values[i], format)}`;
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        ...AXIS_STYLE,
        axisLabel: {
          ...AXIS_STYLE.axisLabel,
          interval: 0,
          rotate: labels.length > 6 ? 25 : 0,
          width: 100,
          overflow: "truncate",
        },
      },
      yAxis: {
        type: "value",
        ...AXIS_STYLE,
        axisLine: { show: false },
        axisLabel: { ...AXIS_STYLE.axisLabel, formatter: axisFmt(format) },
      },
      series: [
        { type: "bar", stack: "w", data: base, itemStyle: { color: "transparent" }, silent: true },
        {
          type: "bar",
          stack: "w",
          data: tot,
          barMaxWidth: 40,
          itemStyle: { color: "#334155", borderRadius: [4, 4, 0, 0] },
        },
        {
          type: "bar",
          stack: "w",
          data: pos,
          barMaxWidth: 40,
          itemStyle: { color: SERIES.consensus, borderRadius: [4, 4, 0, 0] },
        },
        {
          type: "bar",
          stack: "w",
          data: neg,
          barMaxWidth: 40,
          itemStyle: { color: STATUS.critical, borderRadius: [4, 4, 0, 0] },
        },
      ],
    } as EChartsOption;
  }, [labels, values, kinds, format]);
  return <EChart option={option} height={height} />;
}

interface HeatmapProps {
  rows: string[];
  cols: string[];
  cells: { row: string; col: string; value: number | null; label?: string }[];
  mode: "sequential" | "diverging";
  format?: string;
  height?: number;
  max?: number;
  onClick?: (row: string, col: string) => void;
}

export function Heatmap({ rows, cols, cells, mode, format, height = 460, max, onClick }: HeatmapProps) {
  const option = useMemo<EChartsOption>(() => {
    const data = cells
      .filter((c) => c.value != null)
      .map((c) => [cols.indexOf(c.col), rows.indexOf(c.row), c.value as number]);
    const vals = data.map((d) => d[2]);
    const hi = max ?? (mode === "diverging" ? Math.max(0.3, ...vals.map(Math.abs)) : Math.max(0.5, ...vals));
    return {
      grid: { left: 190, right: 90, top: 8, bottom: 72 },
      tooltip: {
        ...TOOLTIP_STYLE,
        formatter: (p: { value: [number, number, number] }) =>
          `<b>${rows[p.value[1]]}</b><br/>${cols[p.value[0]]}<br/>${formatValue(p.value[2], format)}`,
      },
      xAxis: {
        type: "category",
        data: cols,
        ...AXIS_STYLE,
        splitArea: { show: false },
        axisLabel: { ...AXIS_STYLE.axisLabel, rotate: 45, interval: 0, fontSize: 10 },
      },
      yAxis: {
        type: "category",
        data: rows,
        ...AXIS_STYLE,
        axisLabel: { ...AXIS_STYLE.axisLabel, width: 175, overflow: "truncate", interval: 0 },
      },
      visualMap: {
        min: mode === "diverging" ? -hi : 0,
        max: hi,
        calculable: true,
        orient: "vertical",
        right: 0,
        top: "middle",
        itemHeight: 160,
        textStyle: { color: "#64748b", fontSize: 10 },
        formatter: (v: number) => pct(v, 0),
        inRange: { color: mode === "diverging" ? DIVERGING : SEQ_BLUE },
      },
      series: [
        {
          type: "heatmap",
          data,
          itemStyle: { borderColor: "#ffffff", borderWidth: 2, borderRadius: 3 },
          emphasis: { itemStyle: { borderColor: "#0b1220", borderWidth: 1 } },
        },
      ],
    } as EChartsOption;
  }, [rows, cols, cells, mode, format, max]);
  return (
    <EChart
      option={option}
      height={height}
      onClick={
        onClick
          ? (p) => {
              const v = (p.data as number[]) ?? [];
              onClick(rows[v[1]], cols[v[0]]);
            }
          : undefined
      }
    />
  );
}

interface LineProps {
  categories: string[];
  series: BarSeries[];
  format?: string;
  height?: number;
}

export function SimpleLineChart({ categories, series, format, height = 280 }: LineProps) {
  const option = useMemo<EChartsOption>(
    () => ({
      grid: { left: 60, right: 24, top: series.length > 1 ? 36 : 16, bottom: 32 },
      legend:
        series.length > 1 ? { top: 0, left: 0, icon: "roundRect", itemWidth: 14, itemHeight: 8 } : undefined,
      tooltip: { trigger: "axis", ...TOOLTIP_STYLE, valueFormatter: (v: number) => formatValue(v, format) },
      xAxis: {
        type: "category",
        data: categories,
        boundaryGap: false,
        ...AXIS_STYLE,
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        ...AXIS_STYLE,
        axisLine: { show: false },
        axisLabel: { ...AXIS_STYLE.axisLabel, formatter: axisFmt(format) },
      },
      series: series.map((s, i) => ({
        name: s.name,
        type: "line",
        data: s.data,
        showSymbol: false,
        symbolSize: 6,
        lineStyle: { width: 2, color: s.color ?? CATEGORICAL[i], type: s.dashed ? "dashed" : "solid" },
        itemStyle: { color: s.color ?? CATEGORICAL[i] },
      })),
    }),
    [categories, series, format],
  );
  return <EChart option={option} height={height} />;
}
