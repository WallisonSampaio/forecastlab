/**
 * IBCS bridge (waterfall) for price / volume / mix / events (spec §2.2.2, §2.3.4).
 *
 * Totals use their scenario notation (PL outline, AC solid, FC hatch, TG dashed); steps are green
 * (acima) or red (abaixo) with a signed direct label; the category axis names every bar, so there
 * is no legend, no value axis and no gridline.
 * When the totals dwarf the steps (≥ SCALE_BREAK_RATIO), the value axis starts above zero and the
 * total bars carry a white "cut" marker (series id `scale-break`) plus a caption.
 * In a narrow container (columns under BRIDGE_MIN_COLUMN_PX, e.g. the 5/12 "Por que desviou?"
 * panel at 1366 px) the bridge turns horizontal: one row per step, names on the left and values
 * on the right, so neither names nor signed values ever collide.
 * Clicking a step only highlights it; the tooltip explains it (`step.help`).
 */
import { useMemo, useState } from "react";

import { ChartFrame } from "../components/ui";
import { fmtMeasure, signedMeasure, type Measure } from "../lib/format";
import {
  BRIDGE_MIN_COLUMN_PX,
  IBCS,
  bridgeLayout,
  deltaColor,
  escapeHtml,
  notationItemStyle,
  useElementWidth,
  type BridgeBar,
  type Notation,
} from "../lib/ibcs";
import type { BridgeStep } from "../types/deviations";
import { EChart, TOOLTIP_STYLE, type EChartsOption } from "./EChart";

export interface BridgeChartProps {
  steps: BridgeStep[];
  measure: Measure;
  /** Height of the vertical bridge (the horizontal one grows with the number of steps). */
  height?: number;
  ariaLabel: string;
  /** Optional footnote (e.g. the chapter's `visual.data.note`). */
  note?: string;
}

/** White slanted band drawn across the cut total bars (vertical bars / horizontal bars). */
const BREAK_SYMBOL_V = "path://M0,9 L40,1 L40,5 L0,13 Z";
const BREAK_SYMBOL_H = "path://M9,0 L1,40 L5,40 L13,0 Z";
const UNITS_NOTE = "Em unidades não há efeito preço/mix";
/** Room kept right of the longest horizontal bar for its value label ("R$ 106,00 mi"). */
const H_LABEL_PX = 92;
const H_ROW_PX = 36;

const notationOf = (b: BridgeBar): Notation => b.notation ?? (b.key === "compared" ? "FC" : "PL");
const isTotal = (b: BridgeBar) => b.kind !== "delta";
const valueText = (b: BridgeBar, m: Measure) =>
  isTotal(b) ? fmtMeasure(b.value, m) : signedMeasure(b.value, m);

export function BridgeChart({ steps, measure, height = 300, ariaLabel, note }: BridgeChartProps) {
  const { ref, width } = useElementWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);

  // Units carry no price/mix effect: drop those steps if they were sent anyway.
  const visible = useMemo(
    () => (measure === "units" ? steps.filter((s) => s.key !== "mix" && s.key !== "price") : steps),
    [steps, measure],
  );
  const layout = useMemo(() => bridgeLayout(visible), [visible]);
  const n = Math.max(1, layout.bars.length);
  // jsdom never measures (width 0): keep the vertical layout there.
  const horizontal = width > 0 && (width - 16) / n < BRIDGE_MIN_COLUMN_PX;
  const chartHeight = horizontal ? Math.max(160, n * H_ROW_PX + 16) : height;

  const option = useMemo<EChartsOption>(() => {
    const { bars, scaleBreak, base } = layout;
    const avail = (width || 640) - 16;
    const dim = (i: number) => (active === null || active === i ? 1 : 0.32);

    const placeholder = bars.map((b) => (isTotal(b) ? 0 : Math.min(b.start, b.end)));
    const shown = bars.map((b, i) => {
      const total = isTotal(b);
      const below = !total && b.value < 0;
      return {
        value: total ? b.value : Math.abs(b.value),
        itemStyle: total
          ? notationItemStyle(notationOf(b), dim(i))
          : { color: b.key === "challenge" ? IBCS.neutral : deltaColor(b.value), opacity: dim(i) },
        label: {
          show: true,
          // Horizontal: every value sits right of its bar (each step owns its row).
          position: horizontal ? "right" : below ? "bottom" : "top",
          distance: 6,
          formatter: valueText(b, measure),
          color: total ? IBCS.ink : b.key === "challenge" ? IBCS.ink2 : deltaColor(b.value),
          fontSize: 11.5,
          fontWeight: 700,
          opacity: dim(i),
        },
      };
    });
    const minTotal = Math.min(...bars.filter(isTotal).map((b) => b.value));
    const breakAt = base + (minTotal - base) * 0.32;
    const levels = bars.flatMap((b) => (isTotal(b) ? [0, b.end] : [b.start, b.end]));
    const hi = Math.max(0, ...levels);
    const lo = Math.min(0, ...levels);

    const tooltip = {
      ...TOOLTIP_STYLE,
      trigger: "item",
      formatter: (p: { dataIndex: number; seriesId?: string }) => {
        const b = bars[p.dataIndex];
        if (!b || p.seriesId !== "bridge") return "";
        return (
          `<div style="max-width:260px;white-space:normal">` +
          `<b>${escapeHtml(b.label)}</b><br/>${escapeHtml(valueText(b, measure))}` +
          (b.help ? `<div style="margin-top:4px;color:#8489a3">${escapeHtml(b.help)}</div>` : "") +
          `</div>`
        );
      },
    };
    const categoryLabels = bars.map((b) => b.label);

    if (horizontal) {
      const labelW = Math.round(Math.min(132, Math.max(84, avail * 0.3)));
      const plotW = Math.max(80, avail - labelW - 12);
      const start = scaleBreak ? base : lo;
      // Stretch the hidden value axis so the longest bar leaves room for its label.
      const max = hi + ((hi - start) * H_LABEL_PX) / Math.max(1, plotW - H_LABEL_PX);
      const barPx = Math.min(24, H_ROW_PX * 0.62);
      return {
        animationDuration: 400,
        grid: { left: 8, right: 8, top: 8, bottom: 8, containLabel: true },
        tooltip,
        yAxis: {
          type: "category",
          inverse: true,
          data: categoryLabels,
          axisTick: { show: false },
          axisLine: { lineStyle: { color: IBCS.axis } },
          splitLine: { show: false },
          axisLabel: {
            interval: 0,
            width: labelW,
            overflow: "break",
            lineHeight: 14,
            color: IBCS.ink2,
            fontSize: 11.5,
            margin: 10,
          },
        },
        xAxis: {
          type: "value",
          show: false,
          splitLine: { show: false },
          max,
          ...(scaleBreak ? { min: base } : {}),
        },
        series: [
          {
            id: "bridge-base",
            type: "bar",
            stack: "bridge",
            // Stack on the placeholder whatever the sign (levels may cross zero).
            stackStrategy: "all",
            silent: true,
            barWidth: barPx,
            itemStyle: { color: "transparent" },
            emphasis: { disabled: true },
            tooltip: { show: false },
            data: placeholder,
          },
          {
            id: "bridge",
            name: "Ponte",
            type: "bar",
            stack: "bridge",
            // Stack on the placeholder whatever the sign (levels may cross zero).
            stackStrategy: "all",
            barWidth: barPx,
            cursor: "pointer",
            emphasis: { disabled: true },
            data: shown,
          },
          ...(scaleBreak
            ? [
                {
                  id: "scale-break",
                  name: "Quebra de escala",
                  type: "scatter",
                  silent: true,
                  z: 5,
                  symbol: BREAK_SYMBOL_H,
                  symbolSize: [12, barPx + 10],
                  itemStyle: { color: "#ffffff", opacity: 1 },
                  tooltip: { show: false },
                  data: bars.map((b, i) => (isTotal(b) ? [breakAt, i] : null)).filter(Boolean),
                },
              ]
            : []),
        ],
      };
    }

    const catW = Math.max(56, avail / n);
    const barPx = Math.min(64, catW * 0.56);
    return {
      animationDuration: 400,
      // Category labels wrap onto ≤ 2 lines (14 px each) under the bars.
      grid: { left: 8, right: 8, top: 30, bottom: 44, containLabel: false },
      tooltip,
      xAxis: {
        type: "category",
        data: categoryLabels,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: IBCS.axis } },
        splitLine: { show: false },
        axisLabel: {
          interval: 0,
          width: Math.max(48, catW - 10),
          overflow: "break",
          lineHeight: 14,
          color: IBCS.ink2,
          fontSize: 11.5,
          margin: 10,
        },
      },
      yAxis: {
        type: "value",
        show: false,
        splitLine: { show: false },
        ...(scaleBreak ? { min: base } : {}),
      },
      series: [
        {
          id: "bridge-base",
          type: "bar",
          stack: "bridge",
          // Stack on the placeholder whatever the sign (levels may cross zero).
          stackStrategy: "all",
          silent: true,
          barWidth: barPx,
          itemStyle: { color: "transparent" },
          emphasis: { disabled: true },
          tooltip: { show: false },
          data: placeholder,
        },
        {
          id: "bridge",
          name: "Ponte",
          type: "bar",
          stack: "bridge",
          // Stack on the placeholder whatever the sign (levels may cross zero).
          stackStrategy: "all",
          barWidth: barPx,
          cursor: "pointer",
          emphasis: { disabled: true },
          data: shown,
        },
        ...(scaleBreak
          ? [
              {
                id: "scale-break",
                name: "Quebra de escala",
                type: "scatter",
                silent: true,
                z: 5,
                symbol: BREAK_SYMBOL_V,
                symbolSize: [barPx + 10, 12],
                itemStyle: { color: "#ffffff", opacity: 1 },
                tooltip: { show: false },
                data: bars.map((b, i) => (isTotal(b) ? [i, breakAt] : null)).filter(Boolean),
              },
            ]
          : []),
      ],
    };
  }, [layout, measure, width, active, horizontal, n]);

  const notes = [
    measure === "units" ? UNITS_NOTE : null,
    layout.scaleBreak ? "Escala interrompida: as barras de total não começam em zero." : null,
    note ?? null,
  ].filter(Boolean);

  return (
    <ChartFrame
      ariaLabel={ariaLabel}
      columns={[{ label: "Etapa" }, { label: "Valor", align: "right" }, { label: "O que significa" }]}
      rows={layout.bars.map((b) => ({
        key: b.key,
        cells: [b.label, valueText(b, measure), b.help],
      }))}
      note={notes.length ? notes.join(" · ") : undefined}
    >
      <div ref={ref}>
        <EChart
          option={option}
          height={chartHeight}
          ariaLabel={ariaLabel}
          onClick={(p) => {
            if ((p as { seriesId?: string }).seriesId !== "bridge") return;
            setActive((cur) => (cur === p.dataIndex ? null : p.dataIndex));
          }}
        />
      </div>
    </ChartFrame>
  );
}
