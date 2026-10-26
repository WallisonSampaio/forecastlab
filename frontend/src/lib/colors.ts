/**
 * Chart color roles. Categorical slots 1-5 of the validated reference palette
 * (adjacent CVD ΔE ≥ 8 in light and dark). Low-contrast slots are always paired
 * with legend + dash pattern + table view (relief rule).
 */
export const SERIES = {
  actual: "#1b1f3b",
  base: "#2a78d6",
  budget: "#eb6834",
  consensus: "#1baf7a",
  target: "#eda100",
  challenger: "#e87ba4",
  band: "rgba(42,120,214,0.12)",
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
  primary: "#1b1f3b",
  secondary: "#4a4f6a",
  muted: "#8489a3",
  grid: "#eef0f7",
  axis: "#d5daeb",
};

/** Brand tones for 3D icon tiles and pastel tinted surfaces. */
export type Tone = "blue" | "navy" | "yellow" | "green" | "red" | "orange" | "purple" | "pink" | "teal";

export const TONES: Record<Tone, { tile: string; surface: string; text: string; soft: string }> = {
  blue: {
    tile: "from-[#7db4ff] to-[#3483fa] shadow-[0_10px_20px_-8px_rgba(52,131,250,0.75)]",
    surface: "from-white to-[#eaf2ff]",
    text: "text-[#2364d2]",
    soft: "bg-[#eaf2ff] text-[#2364d2]",
  },
  navy: {
    tile: "from-[#6c72d6] to-[#2d3277] shadow-[0_10px_20px_-8px_rgba(45,50,119,0.7)]",
    surface: "from-white to-[#eceefa]",
    text: "text-[#2d3277]",
    soft: "bg-[#eceefa] text-[#2d3277]",
  },
  yellow: {
    tile: "from-[#fff47a] to-[#ffcf00] shadow-[0_10px_20px_-8px_rgba(240,190,0,0.75)] !text-[#2d3277]",
    surface: "from-white to-[#fff9d6]",
    text: "text-[#8a6d00]",
    soft: "bg-[#fff6c2] text-[#7a6100]",
  },
  green: {
    tile: "from-[#6fe3a8] to-[#16b36b] shadow-[0_10px_20px_-8px_rgba(22,179,107,0.7)]",
    surface: "from-white to-[#e7f8ef]",
    text: "text-[#0d8a50]",
    soft: "bg-[#e3f7ec] text-[#0d7a47]",
  },
  red: {
    tile: "from-[#ff9a9a] to-[#ef4444] shadow-[0_10px_20px_-8px_rgba(239,68,68,0.7)]",
    surface: "from-white to-[#fdecec]",
    text: "text-[#c22d2d]",
    soft: "bg-[#fdeaea] text-[#b42323]",
  },
  orange: {
    tile: "from-[#ffc08a] to-[#f97316] shadow-[0_10px_20px_-8px_rgba(249,115,22,0.7)]",
    surface: "from-white to-[#fff1e5]",
    text: "text-[#c25a0d]",
    soft: "bg-[#fff0e3] text-[#b0500a]",
  },
  purple: {
    tile: "from-[#b9a2ff] to-[#7c5cff] shadow-[0_10px_20px_-8px_rgba(124,92,255,0.7)]",
    surface: "from-white to-[#f1edff]",
    text: "text-[#5b3fd6]",
    soft: "bg-[#f0ebff] text-[#5b3fd6]",
  },
  pink: {
    tile: "from-[#ffa6cf] to-[#ec4899] shadow-[0_10px_20px_-8px_rgba(236,72,153,0.65)]",
    surface: "from-white to-[#fdeef6]",
    text: "text-[#be2c74]",
    soft: "bg-[#fdebf4] text-[#b0286b]",
  },
  teal: {
    tile: "from-[#7fe0e6] to-[#0fb5c0] shadow-[0_10px_20px_-8px_rgba(15,181,192,0.65)]",
    surface: "from-white to-[#e6f8f9]",
    text: "text-[#0b8790]",
    soft: "bg-[#e3f6f7] text-[#0a7a82]",
  },
};

/** Target feasibility class style; the badge pairs it with a lucide icon and the label. */
export const CLASS_STYLE: Record<string, { color: string; bg: string; text: string; label: string }> = {
  REALISTIC: {
    color: STATUS.good,
    bg: "bg-emerald-50",
    text: "text-emerald-800",
    label: "Realista",
  },
  STRETCH: {
    color: STATUS.warning,
    bg: "bg-amber-50",
    text: "text-amber-800",
    label: "Desafiadora",
  },
  AGGRESSIVE: {
    color: STATUS.critical,
    bg: "bg-red-50",
    text: "text-red-800",
    label: "Agressiva",
  },
  UNDERESTIMATED: {
    color: STATUS.under,
    bg: "bg-blue-50",
    text: "text-blue-800",
    label: "Subestimada",
  },
};

/** Bias class style; the badge pairs it with a lucide arrow icon and the label (never colour alone). */
export const BIAS_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  Under: { bg: "bg-blue-50", text: "text-blue-800", label: "Subestimado" },
  Balanced: { bg: "bg-emerald-50", text: "text-emerald-800", label: "Equilibrado" },
  Over: { bg: "bg-red-50", text: "text-red-800", label: "Superestimado" },
};

export const CONFIDENCE_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  High: { bg: "bg-emerald-50", text: "text-emerald-800", label: "Alta" },
  Medium: { bg: "bg-amber-50", text: "text-amber-800", label: "Média" },
  Low: { bg: "bg-red-50", text: "text-red-800", label: "Baixa" },
};
