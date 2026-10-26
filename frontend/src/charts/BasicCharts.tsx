import { useMemo, type ReactNode } from "react";

import { CATEGORICAL, DIVERGING, SEQ_BLUE, SERIES, STATUS } from "../lib/colors";
import { compact, formatValue, money, pct } from "../lib/format";
import { AXIS_STYLE, EChart, TOOLTIP_STYLE, verticalGradient, withAlpha, type EChartsOption } from "./EChart";

const axisFmt = (format?: string) => (v: number) =>
  format === "percent" || format === "percent_signed"
    ? pct(v, 0)
    : format === "currency"
      ? money(v)
      : compact(v);

const LEGEND_BASE = {
  top: 0,
  left: 0,
  icon: "roundRect",
  itemWidth: 16,
  itemHeight: 10,
  itemGap: 16,
  textStyle: { color: "#4a4f6a", fontSize: 12 },
};

const MUTED_BAR = "#dfe4f2";

/** Soft gradient for a bar, oriented from its base to its rounded end. */
function barFill(color: string, horizontal: boolean, negative: boolean) {
  const strong = color;
  const soft = withAlpha(color, 0.72);
  if (soft === color) return color; // non-hex colors stay solid
  if (horizontal) {
    return {
      type: "linear",
      x: negative ? 1 : 0,
      y: 0,
      x2: negative ? 0 : 1,
      y2: 0,
      colorStops: [
        { offset: 0, color: soft },
        { offset: 1, color: strong },
      ],
    };
  }
  return negative ? verticalGradient(soft, strong) : verticalGradient(strong, soft);
}

/** Rounded outer end, nearly square base — works for positive and negative bars. */
function barRadius(horizontal: boolean, negative: boolean, stacked: boolean) {
  if (stacked) return 3;
  if (horizontal) return negative ? [8, 2, 2, 8] : [2, 8, 8, 2];
  return negative ? [2, 2, 8, 8] : [8, 8, 2, 2];
}

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
      // Horizontal bars put long pt-BR values ("400,0 mil") side by side: fewer ticks, no overlap.
      splitNumber: horizontal ? 3 : undefined,
      axisLabel: { ...AXIS_STYLE.axisLabel, formatter: axisFmt(format), hideOverlap: true },
    };
    return {
      grid: {
        left: 8,
        right: 24,
        top: series.length > 1 ? 40 : 16,
        bottom: 8,
        containLabel: true,
      },
      legend: series.length > 1 ? LEGEND_BASE : undefined,
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow", shadowStyle: { color: "rgba(52,131,250,0.06)" } },
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
        barGap: "18%",
        emphasis: { focus: "none" },
        data: s.data.map((v, j) => {
          const negative = (v ?? 0) < 0;
          const color = signColors
            ? negative
              ? signColors.negative
              : signColors.positive
            : highlight !== undefined && j !== highlight && series.length === 1
              ? MUTED_BAR
              : (s.color ?? CATEGORICAL[i % CATEGORICAL.length]);
          return {
            value: v,
            itemStyle: {
              color: barFill(color, horizontal, negative),
              borderRadius: barRadius(horizontal, negative, stacked),
            },
          };
        }),
      })),
    } as EChartsOption;
  }, [categories, series, format, horizontal, stacked, signColors, highlight]);
  return (
    <EChart
      option={option}
      height={height}
      ariaLabel="Gráfico de barras"
      onClick={onClick ? (p) => onClick(p.name) : undefined}
    />
  );
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
    const label = {
      show: labels.length <= 10,
      position: "top",
      color: "#4a4f6a",
      fontSize: 10.5,
      fontWeight: 600,
      formatter: (p: { dataIndex: number }) => axisFmt(format)(values[p.dataIndex]),
    };
    const bar = (data: (number | string)[], color: string) => ({
      type: "bar",
      stack: "w",
      data,
      barMaxWidth: 44,
      label,
      itemStyle: { color: verticalGradient(color, withAlpha(color, 0.72)), borderRadius: [8, 8, 2, 2] },
    });
    return {
      grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow", shadowStyle: { color: "rgba(52,131,250,0.06)" } },
        ...TOOLTIP_STYLE,
        formatter: (ps: { dataIndex: number }[]) => {
          const i = ps[0].dataIndex;
          const kind = kinds[i] === "total" ? "Total" : values[i] >= 0 ? "Aumento" : "Redução";
          return `<div style="font-weight:700;color:#1b1f3b">${labels[i]}</div><div style="margin-top:3px;color:#4a4f6a">${kind}: <b style="color:#1b1f3b">${formatValue(values[i], format)}</b></div>`;
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
        bar(tot, "#2d3277"),
        bar(pos, SERIES.consensus),
        bar(neg, STATUS.critical),
      ],
    } as EChartsOption;
  }, [labels, values, kinds, format]);
  return <EChart option={option} height={height} ariaLabel="Gráfico de cascata" />;
}

interface HeatmapProps {
  rows: string[];
  cols: string[];
  cells: { row: string; col: string; value: number | null; label?: string }[];
  mode: "sequential" | "diverging";
  format?: string;
  height?: number;
  max?: number;
  /** Name of the measure shown in the tooltip (e.g. "WMAPE", "Viés"). */
  valueLabel?: string;
  onClick?: (row: string, col: string) => void;
}

export function Heatmap({
  rows,
  cols,
  cells,
  mode,
  format,
  height = 460,
  max,
  valueLabel = "Valor",
  onClick,
}: HeatmapProps) {
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
          `<div style="font-weight:700;color:#1b1f3b">${rows[p.value[1]]}</div><div style="color:#8489a3;margin-top:1px">${cols[p.value[0]]}</div><div style="margin-top:5px;color:#4a4f6a">${valueLabel}: <b style="color:#1b1f3b">${formatValue(p.value[2], format)}</b></div>`,
      },
      xAxis: {
        type: "category",
        data: cols,
        ...AXIS_STYLE,
        splitArea: { show: false },
        splitLine: { show: false },
        axisLine: { show: false },
        axisLabel: { ...AXIS_STYLE.axisLabel, rotate: 45, interval: 0, fontSize: 10 },
      },
      yAxis: {
        type: "category",
        data: rows,
        ...AXIS_STYLE,
        splitLine: { show: false },
        axisLine: { show: false },
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
        itemWidth: 12,
        textStyle: { color: "#8489a3", fontSize: 10 },
        handleStyle: { borderColor: "#ffffff", shadowBlur: 6, shadowColor: "rgba(45,50,119,0.3)" },
        // Heatmaps are percent-based by default (WMAPE, viés); other formats use the pt-BR axis helpers.
        formatter: (v: number) => (!format || format.startsWith("percent") ? pct(v, 0) : axisFmt(format)(v)),
        inRange: { color: mode === "diverging" ? DIVERGING : SEQ_BLUE },
      },
      series: [
        {
          type: "heatmap",
          data,
          itemStyle: { borderColor: "#ffffff", borderWidth: 2.5, borderRadius: 6 },
          emphasis: {
            itemStyle: {
              borderColor: "#1b1f3b",
              borderWidth: 1.5,
              shadowBlur: 8,
              shadowColor: "rgba(45,50,119,0.35)",
            },
          },
        },
      ],
    } as EChartsOption;
  }, [rows, cols, cells, mode, format, max, valueLabel]);
  return (
    <EChart
      option={option}
      height={height}
      ariaLabel="Mapa de calor"
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
      grid: { left: 8, right: 16, top: series.length > 1 ? 40 : 16, bottom: 8, containLabel: true },
      legend: series.length > 1 ? LEGEND_BASE : undefined,
      tooltip: {
        trigger: "axis",
        ...TOOLTIP_STYLE,
        axisPointer: { type: "line", lineStyle: { color: "#c3cae0", type: [4, 4] } },
        valueFormatter: (v: number) => formatValue(v, format),
      },
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
      series: series.map((s, i) => {
        const color = s.color ?? CATEGORICAL[i % CATEGORICAL.length];
        return {
          name: s.name,
          type: "line",
          data: s.data,
          smooth: 0.3,
          showSymbol: false,
          symbol: "circle",
          symbolSize: 7,
          lineStyle: { width: 2.4, color, type: s.dashed ? "dashed" : "solid", cap: "round" },
          itemStyle: { color, borderColor: "#ffffff", borderWidth: 2 },
          ...(series.length === 1 && !s.dashed
            ? { areaStyle: { color: verticalGradient(withAlpha(color, 0.16), withAlpha(color, 0)) } }
            : {}),
        };
      }),
    }),
    [categories, series, format],
  );
  return <EChart option={option} height={height} ariaLabel="Gráfico de linhas" />;
}

/* --------------------------------------------------------------------- donut */
export interface DonutSlice {
  name: string;
  value: number;
  color?: string;
}

interface DonutProps {
  data: DonutSlice[];
  format?: string;
  height?: number;
  /** Small caption shown in the hole (e.g. "Total"). */
  centerLabel?: ReactNode;
  /** Big value shown in the hole. */
  centerValue?: ReactNode;
  /** Legend at the bottom (default) or hidden. */
  legend?: boolean;
  onClick?: (name: string) => void;
}

export function DonutChart({
  data,
  format,
  height = 260,
  centerLabel,
  centerValue,
  legend = true,
  onClick,
}: DonutProps) {
  const cy = legend ? 44 : 50;
  const option = useMemo<EChartsOption>(
    () => ({
      tooltip: {
        trigger: "item",
        ...TOOLTIP_STYLE,
        formatter: (p: { name: string; value: number; percent: number; color: string }) =>
          `<div style="display:flex;align-items:center;gap:7px;font-weight:700;color:#1b1f3b"><span style="display:inline-block;width:9px;height:9px;border-radius:999px;background:${p.color}"></span>${p.name}</div><div style="margin-top:3px;color:#4a4f6a"><b style="color:#1b1f3b">${formatValue(p.value, format)}</b> · ${pct(p.percent / 100)}</div>`,
      },
      legend: legend
        ? {
            bottom: 0,
            left: "center",
            icon: "circle",
            itemWidth: 10,
            itemHeight: 10,
            itemGap: 14,
            textStyle: { color: "#4a4f6a", fontSize: 12 },
          }
        : undefined,
      series: [
        {
          type: "pie",
          radius: ["60%", "82%"],
          center: ["50%", `${cy}%`],
          avoidLabelOverlap: true,
          padAngle: 2,
          itemStyle: { borderRadius: 10, borderColor: "#ffffff", borderWidth: 2 },
          label: { show: false },
          labelLine: { show: false },
          emphasis: { scale: true, scaleSize: 6 },
          data: data.map((d, i) => ({
            name: d.name,
            value: d.value,
            itemStyle: { color: d.color ?? CATEGORICAL[i % CATEGORICAL.length] },
          })),
        },
      ],
    }),
    [data, format, legend, cy],
  );
  return (
    <div className="relative">
      <EChart
        option={option}
        height={height}
        ariaLabel="Gráfico de rosca"
        onClick={onClick ? (p) => onClick(p.name) : undefined}
      />
      {(centerLabel || centerValue) && (
        <div
          className="pointer-events-none absolute inset-x-0 flex -translate-y-1/2 flex-col items-center text-center"
          style={{ top: `${cy}%` }}
        >
          {centerValue && <div className="text-xl font-bold tracking-tight text-ink">{centerValue}</div>}
          {centerLabel && <div className="text-[11px] font-medium text-muted">{centerLabel}</div>}
        </div>
      )}
    </div>
  );
}
