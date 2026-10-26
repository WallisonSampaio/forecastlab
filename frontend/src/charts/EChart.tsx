import { BarChart, HeatmapChart, LineChart, PieChart, ScatterChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { LabelLayout } from "echarts/features";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

echarts.use([
  LineChart,
  BarChart,
  HeatmapChart,
  ScatterChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  MarkAreaComponent,
  VisualMapComponent,
  DataZoomComponent,
  // `labelLayout` (moveOverlap / hideOverlap): direct end labels of the journey charts.
  LabelLayout,
  CanvasRenderer,
]);

export type EChartsOption = echarts.EChartsCoreOption;

interface Props {
  option: EChartsOption;
  height?: number | string;
  className?: string;
  onClick?: (params: { name: string; seriesName?: string; data?: unknown; dataIndex: number }) => void;
  ariaLabel?: string;
}

/** Soft-UI axis style: hairline axis, muted labels, light dashed grid. */
export const AXIS_STYLE = {
  axisLine: { lineStyle: { color: "#dfe3f0" } },
  axisTick: { show: false },
  axisLabel: { color: "#8489a3", fontSize: 11, margin: 12 },
  splitLine: { lineStyle: { color: "#eef0f7", type: [4, 4] as number[] } },
};

/** Glassy rounded tooltip with a soft navy shadow. */
export const TOOLTIP_STYLE = {
  backgroundColor: "rgba(255,255,255,0.97)",
  borderColor: "#e7eaf5",
  borderWidth: 1,
  borderRadius: 14,
  padding: [10, 14],
  textStyle: { color: "#1b1f3b", fontSize: 12 },
  extraCssText:
    "box-shadow:0 18px 40px -14px rgba(45,50,119,0.32),0 2px 6px -2px rgba(45,50,119,0.08);border-radius:14px;backdrop-filter:blur(8px);",
};

/** Vertical gradient fill (top -> bottom) used for soft areas under lines and bars. */
export function verticalGradient(top: string, bottom: string) {
  return {
    type: "linear",
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: top },
      { offset: 1, color: bottom },
    ],
  };
}

/** "#rrggbb" + alpha -> "rgba(...)"; other color strings pass through unchanged. */
export function withAlpha(color: string, alpha: number): string {
  const m = /^#([0-9a-f]{6})$/i.exec(color);
  if (!m) return color;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

export function EChart({ option, height = 320, className, onClick, ariaLabel }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const clickRef = useRef(onClick);
  clickRef.current = onClick;

  useEffect(() => {
    if (!ref.current) return;
    const c = echarts.init(ref.current, undefined, { renderer: "canvas" });
    chart.current = c;
    c.on("click", (p) => clickRef.current?.(p as never));
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      c.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    chart.current?.setOption(
      {
        textStyle: { fontFamily: "Inter Variable, system-ui, sans-serif", color: "#4a4f6a" },
        animationDuration: 500,
        animationEasing: "cubicOut",
        ...option,
      },
      { notMerge: true },
    );
  }, [option]);

  return (
    <div
      ref={ref}
      role="img"
      aria-label={ariaLabel}
      className={className}
      style={{ height, width: "100%" }}
    />
  );
}
