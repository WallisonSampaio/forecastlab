import { BarChart, HeatmapChart, LineChart, ScatterChart } from "echarts/charts";
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
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

echarts.use([
  LineChart,
  BarChart,
  HeatmapChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  MarkAreaComponent,
  VisualMapComponent,
  DataZoomComponent,
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

export const AXIS_STYLE = {
  axisLine: { lineStyle: { color: "#cbd5e1" } },
  axisTick: { show: false },
  axisLabel: { color: "#64748b", fontSize: 11 },
  splitLine: { lineStyle: { color: "#eef0f3" } },
};

export const TOOLTIP_STYLE = {
  backgroundColor: "#ffffff",
  borderColor: "#e5e7eb",
  borderWidth: 1,
  padding: [8, 12],
  textStyle: { color: "#0b1220", fontSize: 12 },
  extraCssText: "box-shadow:0 8px 24px rgba(15,23,42,0.12);border-radius:10px;",
};

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
        textStyle: { fontFamily: "Inter Variable, system-ui, sans-serif" },
        animationDuration: 350,
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
