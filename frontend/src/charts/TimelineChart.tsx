import { Table2, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";

import { SERIES } from "../lib/colors";
import { compact, fmtMeasure, shortMonth, type Measure } from "../lib/format";
import type { TimelineRow } from "../types";
import { AXIS_STYLE, EChart, TOOLTIP_STYLE, type EChartsOption } from "./EChart";

export type SeriesKey =
  "actual" | "base" | "consensus" | "budget" | "target" | "challenger" | "backtest" | "band";

const DEF: Record<
  Exclude<SeriesKey, "band">,
  { name: string; color: string; type?: string; width: number }
> = {
  actual: { name: "Actual", color: SERIES.actual, width: 2.2 },
  base: { name: "Statistical Forecast", color: SERIES.base, width: 2 },
  consensus: { name: "Consensus Forecast", color: SERIES.consensus, width: 2.4 },
  budget: { name: "Budget", color: SERIES.budget, type: "dashed", width: 1.8 },
  target: { name: "Target", color: SERIES.target, type: [8, 4, 2, 4] as unknown as string, width: 1.8 },
  challenger: { name: "Challenger", color: SERIES.challenger, type: "dotted", width: 1.8 },
  backtest: { name: "Backtest (out-of-sample)", color: SERIES.base, type: "dotted", width: 1.6 },
};
const BAND_NAME = "P10–P90 range";

interface Props {
  rows: TimelineRow[];
  measure: Measure;
  lastActual?: string;
  height?: number;
  hidden?: SeriesKey[];
  show?: SeriesKey[];
  title?: string;
}

const DEFAULT_HIDDEN: SeriesKey[] = ["challenger", "backtest"];
const DEFAULT_SHOW: SeriesKey[] = [
  "actual",
  "base",
  "consensus",
  "budget",
  "target",
  "challenger",
  "backtest",
  "band",
];

export function TimelineChart({
  rows,
  measure,
  lastActual,
  height = 360,
  hidden: hiddenProp,
  show: showProp,
}: Props) {
  const [tableView, setTableView] = useState(false);
  const hiddenKey = (hiddenProp ?? DEFAULT_HIDDEN).join(",");
  const showKey = (showProp ?? DEFAULT_SHOW).join(",");
  const option = useMemo<EChartsOption>(() => {
    const hidden = hiddenKey.split(",") as SeriesKey[];
    const show = showKey.split(",") as SeriesKey[];
    const x = rows.map((r) => r.date.slice(0, 10));
    const lastIdx = lastActual ? x.indexOf(lastActual.slice(0, 10)) : -1;
    const series: unknown[] = [];
    const selected: Record<string, boolean> = {};
    if (show.includes("band") && rows.some((r) => r.p10 != null)) {
      series.push({
        name: "P10",
        type: "line",
        data: rows.map((r) => r.p10 ?? null),
        stack: "band",
        lineStyle: { opacity: 0 },
        symbol: "none",
        silent: true,
        tooltip: { show: false },
      });
      series.push({
        name: BAND_NAME,
        type: "line",
        data: rows.map((r) => (r.p90 != null && r.p10 != null ? r.p90 - r.p10 : null)),
        stack: "band",
        lineStyle: { opacity: 0 },
        symbol: "none",
        areaStyle: { color: SERIES.band },
        itemStyle: { color: "rgba(42,120,214,0.35)" },
        tooltip: { show: false },
      });
      selected[BAND_NAME] = !hidden.includes("band");
    }
    (Object.keys(DEF) as (keyof typeof DEF)[]).forEach((key) => {
      if (!show.includes(key)) return;
      const data = rows.map((r) => (r[key] as number | null | undefined) ?? null);
      if (!data.some((v) => v != null)) return;
      const d = DEF[key];
      series.push({
        name: d.name,
        type: "line",
        data,
        symbol: "circle",
        symbolSize: 6,
        showSymbol: false,
        connectNulls: false,
        z: key === "actual" ? 5 : key === "consensus" ? 4 : 3,
        lineStyle: { color: d.color, width: d.width, type: d.type ?? "solid" },
        itemStyle: { color: d.color },
        emphasis: { focus: "none" },
        ...(key === "actual" && lastIdx >= 0
          ? {
              markLine: {
                silent: true,
                symbol: "none",
                lineStyle: { color: "#94a3b8", type: "solid", width: 1 },
                label: { formatter: "Forecast →", color: "#64748b", fontSize: 11, position: "insideEndTop" },
                data: [{ xAxis: lastIdx }],
              },
            }
          : {}),
      });
      selected[d.name] = !hidden.includes(key);
    });
    return {
      grid: { left: 56, right: 24, top: 48, bottom: 32 },
      legend: {
        top: 0,
        left: 0,
        itemWidth: 18,
        itemHeight: 8,
        icon: "roundRect",
        textStyle: { color: "#334155", fontSize: 12 },
        selected,
        data: series.map((s) => (s as { name: string }).name).filter((n) => n !== "P10"),
      },
      tooltip: {
        trigger: "axis",
        ...TOOLTIP_STYLE,
        axisPointer: { type: "line", lineStyle: { color: "#94a3b8" } },
        formatter: (
          params: { axisValue: string; seriesName: string; value: number | null; color: string }[],
        ) => {
          const date = params[0]?.axisValue;
          const row = rows.find((r) => r.date.slice(0, 10) === date);
          const lines = params
            .filter((p) => p.seriesName !== "P10" && p.seriesName !== BAND_NAME && p.value != null)
            .map(
              (p) =>
                `<div style="display:flex;justify-content:space-between;gap:16px"><span><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${p.color};margin-right:6px"></span>${p.seriesName}</span><b>${fmtMeasure(p.value, measure)}</b></div>`,
            );
          if (row?.p10 != null && row?.p90 != null)
            lines.push(
              `<div style="display:flex;justify-content:space-between;gap:16px;color:#64748b"><span>P10 – P90</span><span>${fmtMeasure(row.p10, measure)} – ${fmtMeasure(row.p90, measure)}</span></div>`,
            );
          return `<div style="font-weight:600;margin-bottom:4px">${shortMonth(date)}</div>${lines.join("")}`;
        },
      },
      xAxis: {
        type: "category",
        data: x,
        boundaryGap: false,
        ...AXIS_STYLE,
        splitLine: { show: false },
        axisLabel: { ...AXIS_STYLE.axisLabel, formatter: (v: string) => shortMonth(v) },
      },
      yAxis: {
        type: "value",
        ...AXIS_STYLE,
        axisLine: { show: false },
        axisLabel: {
          ...AXIS_STYLE.axisLabel,
          formatter: (v: number) => (measure === "revenue" ? `R$${compact(v)}` : compact(v)),
        },
      },
      series,
    } as EChartsOption;
  }, [rows, measure, lastActual, hiddenKey, showKey]);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setTableView((v) => !v)}
        className="btn-ghost absolute right-0 top-0 z-10 px-2 py-1 text-xs"
        title={tableView ? "Show chart" : "Show data table"}
      >
        {tableView ? <TrendingUp size={14} /> : <Table2 size={14} />}
        {tableView ? "Chart" : "Table"}
      </button>
      {tableView ? (
        <div className="max-h-[360px] overflow-auto pt-8" style={{ height }}>
          <table className="table-base tabular">
            <thead>
              <tr>
                <th>Month</th>
                {(["actual", "base", "consensus", "p10", "p90", "budget", "target"] as const).map((k) => (
                  <th key={k} className="text-right">
                    {k === "base" ? "Statistical" : k}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.date}>
                  <td>{shortMonth(r.date)}</td>
                  {(["actual", "base", "consensus", "p10", "p90", "budget", "target"] as const).map((k) => (
                    <td key={k} className="text-right">
                      {fmtMeasure(r[k] as number | null, measure)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EChart
          option={option}
          height={height}
          ariaLabel="Demand timeline: actual, forecasts, budget and target"
        />
      )}
    </div>
  );
}
