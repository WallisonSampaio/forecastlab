import clsx from "clsx";
import { Table2, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";

import { SERIES } from "../lib/colors";
import { fmtMeasure, money, compact, monthLabel, shortMonth, type Measure } from "../lib/format";
import type { TimelineRow } from "../types";
import { AXIS_STYLE, EChart, TOOLTIP_STYLE, verticalGradient, withAlpha, type EChartsOption } from "./EChart";

export type SeriesKey =
  "actual" | "base" | "consensus" | "budget" | "target" | "challenger" | "backtest" | "band";

type LineKey = Exclude<SeriesKey, "band">;

const DEF: Record<
  LineKey,
  { name: string; color: string; type?: string | number[]; dash?: string; width: number; area?: number }
> = {
  actual: { name: "Real", color: SERIES.actual, width: 2.4, area: 0.07 },
  base: { name: "Forecast estatístico", color: SERIES.base, width: 2 },
  consensus: { name: "Forecast de consenso", color: SERIES.consensus, width: 2.6, area: 0.16 },
  budget: { name: "Orçamento", color: SERIES.budget, type: "dashed", dash: "6 4", width: 1.9 },
  target: { name: "Meta", color: SERIES.target, type: [8, 4, 2, 4], dash: "8 4 2 4", width: 1.9 },
  challenger: { name: "Desafiante", color: SERIES.challenger, type: "dotted", dash: "1.5 3.5", width: 2 },
  backtest: {
    name: "Backtest (fora da amostra)",
    color: SERIES.base,
    type: "dotted",
    dash: "1.5 3.5",
    width: 1.8,
  },
};
const BAND_NAME = "Faixa P10–P90";
const ORDER: SeriesKey[] = [
  "band",
  "actual",
  "base",
  "consensus",
  "budget",
  "target",
  "challenger",
  "backtest",
];

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

const TABLE_COLS: { key: keyof TimelineRow; label: string }[] = [
  { key: "actual", label: "Real" },
  { key: "base", label: "Estatístico" },
  { key: "consensus", label: "Consenso" },
  { key: "p10", label: "P10" },
  { key: "p90", label: "P90" },
  { key: "budget", label: "Orçamento" },
  { key: "target", label: "Meta" },
];

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Legend swatch that mirrors the line style (color + dash pattern), never color alone. */
function Swatch({ k }: { k: SeriesKey }) {
  if (k === "band") {
    return (
      <span
        aria-hidden
        className="inline-block h-2.5 w-[22px] rounded-full"
        style={{ background: "rgba(42,120,214,0.28)" }}
      />
    );
  }
  const d = DEF[k];
  return (
    <svg aria-hidden width="24" height="10" viewBox="0 0 24 10" className="shrink-0">
      <line
        x1="2"
        y1="5"
        x2="22"
        y2="5"
        stroke={d.color}
        strokeWidth={Math.max(2.2, d.width)}
        strokeLinecap="round"
        strokeDasharray={d.dash}
      />
    </svg>
  );
}

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
  // Series switched off by the user; resets whenever the caller changes `hidden`.
  const [offState, setOffState] = useState<{ key: string; off: Set<SeriesKey> }>(() => ({
    key: hiddenKey,
    off: new Set(hiddenKey.split(",") as SeriesKey[]),
  }));
  const off = offState.key === hiddenKey ? offState.off : new Set(hiddenKey.split(",") as SeriesKey[]);

  // Series that are requested AND have data, in a stable legend order.
  const available = useMemo<SeriesKey[]>(() => {
    const show = showKey.split(",") as SeriesKey[];
    return ORDER.filter((k) => {
      if (!show.includes(k)) return false;
      if (k === "band") return rows.some((r) => r.p10 != null && r.p90 != null);
      return rows.some((r) => r[k] != null);
    });
  }, [rows, showKey]);

  const offKey = [...off].sort().join(",");
  const option = useMemo<EChartsOption>(() => {
    const hidden = new Set(offKey.split(",") as SeriesKey[]);
    const x = rows.map((r) => r.date.slice(0, 10));
    const lastIdx = lastActual ? x.indexOf(lastActual.slice(0, 10)) : -1;
    const series: unknown[] = [];
    const selected: Record<string, boolean> = {};
    if (available.includes("band")) {
      series.push({
        name: "P10",
        type: "line",
        data: rows.map((r) => r.p10 ?? null),
        stack: "band",
        smooth: 0.3,
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
        smooth: 0.3,
        lineStyle: { opacity: 0 },
        symbol: "none",
        silent: true,
        areaStyle: { color: SERIES.band },
        itemStyle: { color: "rgba(42,120,214,0.35)" },
        tooltip: { show: false },
      });
      selected.P10 = !hidden.has("band");
      selected[BAND_NAME] = !hidden.has("band");
    }
    available.forEach((key) => {
      if (key === "band") return;
      const d = DEF[key];
      series.push({
        name: d.name,
        type: "line",
        data: rows.map((r) => (r[key] as number | null | undefined) ?? null),
        smooth: 0.3,
        symbol: "circle",
        symbolSize: 7,
        showSymbol: false,
        connectNulls: false,
        z: key === "actual" ? 5 : key === "consensus" ? 4 : 3,
        lineStyle: { color: d.color, width: d.width, type: d.type ?? "solid", cap: "round" },
        itemStyle: { color: d.color, borderColor: "#ffffff", borderWidth: 2 },
        emphasis: { focus: "none", scale: 1.4 },
        ...(d.area
          ? { areaStyle: { color: verticalGradient(withAlpha(d.color, d.area), withAlpha(d.color, 0)) } }
          : {}),
      });
      selected[d.name] = !hidden.has(key);
    });
    // Helper series that only carries the "forecast starts here" marker, so it stays visible
    // whatever series the user switches off.
    if (lastIdx >= 0) {
      series.push({
        name: "__split",
        type: "line",
        data: [],
        silent: true,
        tooltip: { show: false },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: "#aab2cc", type: [4, 4], width: 1.2 },
          label: {
            formatter: "Previsão →",
            color: "#4a4f6a",
            fontSize: 11,
            fontWeight: 600,
            position: "insideEndTop",
            backgroundColor: "rgba(255,255,255,0.9)",
            borderRadius: 8,
            padding: [3, 8],
          },
          data: [{ xAxis: lastIdx }],
        },
        markArea: {
          silent: true,
          itemStyle: { color: "rgba(52,131,250,0.045)" },
          data: [[{ xAxis: lastIdx }, { xAxis: x.length - 1 }]],
        },
      });
    }
    return {
      grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
      legend: { show: false, selected },
      tooltip: {
        trigger: "axis",
        ...TOOLTIP_STYLE,
        axisPointer: { type: "line", lineStyle: { color: "#c3cae0", type: [4, 4] } },
        formatter: (
          params: { axisValue: string; seriesName: string; value: number | null; color: string }[],
        ) => {
          const date = params[0]?.axisValue;
          if (!date) return "";
          const row = rows.find((r) => r.date.slice(0, 10) === date);
          const lines = params
            .filter(
              (p) =>
                p.seriesName !== "P10" &&
                p.seriesName !== BAND_NAME &&
                p.seriesName !== "__split" &&
                p.value != null,
            )
            .map(
              (p) =>
                `<div style="display:flex;justify-content:space-between;align-items:center;gap:18px;margin-top:3px"><span style="color:#4a4f6a"><span style="display:inline-block;width:9px;height:9px;border-radius:999px;background:${p.color};margin-right:7px"></span>${p.seriesName}</span><b style="color:#1b1f3b">${fmtMeasure(p.value, measure)}</b></div>`,
            );
          if (!hidden.has("band") && row?.p10 != null && row?.p90 != null)
            lines.push(
              `<div style="display:flex;justify-content:space-between;gap:18px;margin-top:6px;padding-top:6px;border-top:1px solid #eef0f7;color:#8489a3"><span>${BAND_NAME}</span><span>${fmtMeasure(row.p10, measure)} – ${fmtMeasure(row.p90, measure)}</span></div>`,
            );
          return `<div style="font-weight:700;color:#1b1f3b;margin-bottom:4px">${capitalize(monthLabel(date, "long"))}</div>${lines.join("")}`;
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
          formatter: (v: number) => (measure === "revenue" ? money(v) : compact(v)),
        },
      },
      series,
    } as EChartsOption;
  }, [rows, measure, lastActual, available, offKey]);

  const toggle = (k: SeriesKey) => {
    const next = new Set(off);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    setOffState({ key: hiddenKey, off: next });
  };

  return (
    <div className="min-w-0">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        {!tableView ? (
          <div
            className="flex min-w-0 flex-wrap items-center gap-1.5"
            role="group"
            aria-label="Séries do gráfico"
          >
            {available.map((k) => {
              const name = k === "band" ? BAND_NAME : DEF[k].name;
              const active = !off.has(k);
              return (
                <button
                  key={k}
                  type="button"
                  aria-pressed={active}
                  onClick={() => toggle(k)}
                  title={active ? `Ocultar ${name}` : `Mostrar ${name}`}
                  className={clsx(
                    "inline-flex items-center gap-2 whitespace-nowrap rounded-full border px-3 py-1 text-xs font-medium transition",
                    active
                      ? "border-white/90 bg-white text-ink-2 shadow-[0_4px_12px_-8px_rgba(45,50,119,0.45)] hover:text-ink"
                      : "border-dashed border-line bg-transparent text-muted opacity-60 hover:opacity-100",
                  )}
                >
                  <Swatch k={k} />
                  {name}
                </button>
              );
            })}
          </div>
        ) : (
          <div className="text-xs font-medium text-muted">Valores mensais por série</div>
        )}
        <div
          className="ml-auto inline-flex rounded-xl bg-[#eef1fa] p-1"
          role="tablist"
          aria-label="Visualização"
        >
          {[
            { v: false, label: "Gráfico", icon: <TrendingUp size={13} /> },
            { v: true, label: "Tabela", icon: <Table2 size={13} /> },
          ].map((o) => (
            <button
              key={o.label}
              type="button"
              role="tab"
              aria-selected={tableView === o.v}
              onClick={() => setTableView(o.v)}
              title={o.v ? "Mostrar tabela de dados" : "Mostrar gráfico"}
              className={clsx(
                "inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-semibold transition",
                tableView === o.v
                  ? "bg-white text-ink shadow-[0_4px_10px_-4px_rgba(45,50,119,0.3)]"
                  : "text-muted hover:text-ink",
              )}
            >
              {o.icon}
              {o.label}
            </button>
          ))}
        </div>
      </div>
      {tableView ? (
        <div className="overflow-auto rounded-2xl border border-line bg-white/70" style={{ height }}>
          <table className="table-base tabular">
            <thead>
              <tr>
                <th>Mês</th>
                {TABLE_COLS.map((c) => (
                  <th key={c.key} className="text-right">
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.date}>
                  <td className="font-medium text-ink-2">{monthLabel(r.date)}</td>
                  {TABLE_COLS.map((c) => (
                    <td key={c.key} className="text-right">
                      {fmtMeasure(r[c.key] as number | null, measure)}
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
          ariaLabel="Linha do tempo da demanda: real, forecasts, orçamento e meta"
        />
      )}
    </div>
  );
}
