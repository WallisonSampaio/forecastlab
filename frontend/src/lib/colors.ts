/**
 * Chart color roles. Categorical slots 1-5 of the validated reference palette
 * (adjacent CVD ΔE ≥ 8 in light and dark). Low-contrast slots are always paired
 * with legend + dash pattern + table view (relief rule).
 */
export const SERIES = {
  actual: "#0b1220",
  base: "#2a78d6",
  budget: "#eb6834",
  consensus: "#1baf7a",
  target: "#eda100",
  challenger: "#e87ba4",
  band: "rgba(42,120,214,0.13)",
} as const;

export const CATEGORICAL = [
  "#2a78d6",
  "#eb6834",
  "#1baf7a",
  "#eda100",
  "#e87ba4",
  "#008300",
  "#6250d6",
  "#e34948",
];

export const STATUS = {
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
  under: "#2a78d6",
} as const;

/** Sequential blue ramp (light -> dark) for magnitude (e.g. WMAPE heatmap). */
export const SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
/** Diverging blue <-> red with neutral gray midpoint (bias). */
export const DIVERGING = ["#184f95", "#3987e5", "#9ec5f4", "#ecebe7", "#f3a5a4", "#e34948", "#a32a29"];

export const INK = {
  primary: "#0b1220",
  secondary: "#475569",
  muted: "#94a3b8",
  grid: "#eef0f3",
  axis: "#cbd5e1",
};

export const CLASS_STYLE: Record<
  string,
  { color: string; bg: string; text: string; icon: string; label: string }
> = {
  REALISTIC: {
    color: STATUS.good,
    bg: "bg-emerald-50",
    text: "text-emerald-800",
    icon: "🟢",
    label: "Realistic",
  },
  STRETCH: { color: STATUS.warning, bg: "bg-amber-50", text: "text-amber-800", icon: "🟡", label: "Stretch" },
  AGGRESSIVE: {
    color: STATUS.critical,
    bg: "bg-red-50",
    text: "text-red-800",
    icon: "🔴",
    label: "Aggressive",
  },
  UNDERESTIMATED: {
    color: STATUS.under,
    bg: "bg-blue-50",
    text: "text-blue-800",
    icon: "🔵",
    label: "Underestimated",
  },
};

export const BIAS_STYLE: Record<string, { bg: string; text: string; icon: string; label: string }> = {
  Under: { bg: "bg-blue-50", text: "text-blue-800", icon: "🔵", label: "Under forecast" },
  Balanced: { bg: "bg-emerald-50", text: "text-emerald-800", icon: "🟢", label: "Balanced" },
  Over: { bg: "bg-red-50", text: "text-red-800", icon: "🔴", label: "Over forecast" },
};

export const CONFIDENCE_STYLE: Record<string, { bg: string; text: string }> = {
  High: { bg: "bg-emerald-50", text: "text-emerald-800" },
  Medium: { bg: "bg-amber-50", text: "text-amber-800" },
  Low: { bg: "bg-red-50", text: "text-red-800" },
};
