import { CATEGORICAL, SERIES, STATUS } from "../lib/colors";
import type { ChartSpec } from "../types";
import { BarChart, SimpleLineChart, WaterfallChart } from "./BasicCharts";

const NAMED: Record<string, string> = {
  Actual: SERIES.actual,
  Real: SERIES.actual,
  Base: SERIES.base,
  Consensus: SERIES.consensus,
  Budget: SERIES.budget,
  Orçamento: SERIES.budget,
  Target: SERIES.target,
  Meta: SERIES.target,
  Scenario: SERIES.consensus,
  Cenário: SERIES.consensus,
};

/** Renders a chart spec produced by the AI Analyst (dynamic charts). */
export function ChartRenderer({ spec, height = 300 }: { spec: ChartSpec; height?: number }) {
  const x = spec.x ?? [];
  const series = (spec.series ?? []).map((s, i) => ({
    name: s.name,
    data: s.data,
    dashed: s.dashed,
    color: NAMED[s.name] ?? CATEGORICAL[i % CATEGORICAL.length],
  }));
  if (spec.type === "waterfall") {
    return (
      <WaterfallChart
        labels={x}
        values={(series[0]?.data ?? []).map((v) => v ?? 0)}
        kinds={spec.kinds ?? []}
        format={spec.format}
        height={height}
      />
    );
  }
  if (spec.type === "line") {
    return <SimpleLineChart categories={x} series={series} format={spec.format} height={height} />;
  }
  const signed =
    spec.format === "percent_signed" ||
    (spec.format === "currency" && series[0]?.data.some((v) => (v ?? 0) < 0));
  // Bias: over-forecast (positive) is red, under-forecast blue. Gaps / FVA: positive is good.
  const isBias = /bias|viés/i.test(spec.title ?? "");
  const signColors = isBias
    ? { positive: STATUS.critical, negative: SERIES.base }
    : { positive: STATUS.good, negative: STATUS.critical };
  return (
    <BarChart
      categories={x}
      series={series}
      format={spec.format}
      horizontal={spec.horizontal}
      highlight={spec.highlight}
      signColors={signed ? signColors : undefined}
      height={spec.horizontal ? Math.max(220, x.length * 30 + 40) : height}
    />
  );
}
