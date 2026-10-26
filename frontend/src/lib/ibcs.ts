/**
 * IBCS notation tokens for the journey charts (spec §2.0 "IBCS notation tokens").
 * The tools keep `SERIES` (lib/colors.ts); only Entrada, Relatório and Desvios use this kit.
 *
 *   AC  Real          solid ink
 *   PY  Ano anterior  solid light gray
 *   PL  Orçamento     white fill, 1.5 px ink outline
 *   TG  Meta          white fill, 1.5 px dashed ink outline (or a dashed tick)
 *   FC  Consenso      hatched (ECharts decal / `.ibcs-hatch` in HTML)
 *   Δ   acima/abaixo  green / red, always with a sign
 *   error direction   Superestimou red / Subestimou blue (never green: both are errors)
 *   cause groups      Controlável brand / Inerente gray / Sem causa light hatch
 */
import { useCallback, useEffect, useState } from "react";

import { STATUS } from "./colors";
import { aboveBelow, signedMeasure, type Measure } from "./format";
import type { BridgeStep } from "../types/deviations";

export type Notation = "AC" | "PY" | "PL" | "TG" | "FC";

export const IBCS = {
  ink: "#1b1f3b",
  ink2: "#4a4f6a",
  muted: "#8489a3",
  axis: "#d5daeb",
  py: "#c3c8d9",
  white: "#ffffff",
  /** Outline width of PL/TG/FC shapes (px). */
  border: 1.5,
  /** Favourable Δ ("acima"). */
  good: STATUS.good,
  /** Unfavourable Δ ("abaixo"). */
  bad: STATUS.critical,
  /** Forecast above the actual. */
  over: "#e34948",
  /** Forecast below the actual. */
  under: "#2a78d6",
  /** Definitional steps that are not a performance variance (e.g. "Desafio comercial"). */
  neutral: "#a3a8bf",
  controllable: "#3483fa",
  inherent: "#a3a8bf",
} as const;

export const NOTATION_LABEL: Record<Notation, string> = {
  AC: "Real",
  PY: "Ano anterior",
  PL: "Orçamento",
  TG: "Meta",
  FC: "Consenso",
};

/** Hatch of the FC scenario as an ECharts decal (spec token, verbatim). */
export const FC_DECAL = {
  symbol: "rect",
  dashArrayX: [1, 0],
  dashArrayY: [2, 3],
  rotation: -Math.PI / 4,
  color: IBCS.ink,
};

/** Focus ring of the selected element (only that one). */
export const FOCUS_RING = "ring-2 ring-brand ring-offset-2";

/** Chart declutter: at most this many categories, then "Demais (n)". */
export const MAX_CATEGORIES = 12;

/** Bridge totals at least this many times the largest step get a scale break. */
export const SCALE_BREAK_RATIO = 10;

/**
 * Narrowest column (px) of a vertical bridge. Below it, signed value labels of neighbouring
 * steps collide and category names break mid-word, so the bridge is drawn horizontally
 * (one row per step, names on the left): e.g. the 8-step Meta bridge in the 5/12 panel at 1366 px.
 */
export const BRIDGE_MIN_COLUMN_PX = 92;

/** ECharts `itemStyle` of a bar drawn in a scenario's notation. */
export function notationItemStyle(n: Notation, opacity = 1): Record<string, unknown> {
  switch (n) {
    case "AC":
      return { color: IBCS.ink, opacity };
    case "PY":
      return { color: IBCS.py, opacity };
    case "PL":
      return { color: IBCS.white, borderColor: IBCS.ink, borderWidth: IBCS.border, opacity };
    case "TG":
      return {
        color: IBCS.white,
        borderColor: IBCS.ink,
        borderWidth: IBCS.border,
        borderType: "dashed",
        opacity,
      };
    case "FC":
      return {
        color: IBCS.white,
        borderColor: IBCS.ink,
        borderWidth: IBCS.border,
        decal: FC_DECAL,
        opacity,
      };
  }
}

/** Tailwind classes of an HTML swatch in a scenario's notation (keys and table chips). */
export const NOTATION_SWATCH: Record<Notation, string> = {
  AC: "bg-[#1b1f3b]",
  PY: "bg-[#c3c8d9]",
  PL: "border-[1.5px] border-[#1b1f3b] bg-white",
  TG: "border-[1.5px] border-dashed border-[#1b1f3b] bg-white",
  FC: "ibcs-hatch border-[1.5px] border-[#1b1f3b]",
};

/** Δ colour: green above the reference, red below. Always paired with a sign and a word. */
export const deltaColor = (v: number) => (v < 0 ? IBCS.bad : IBCS.good);

/** Forecast-error colour by sign of `forecast − actual`. */
export const errorColor = (v: number) => (v > 0 ? IBCS.over : IBCS.under);

/** "Superestimou" (forecast above the actual) / "Subestimou". */
export const errorWord = (v: number) => (v > 0 ? "superestimou" : "subestimou");

/** "-R$ 1,58 mi abaixo" · "+1,2 mil acima": sign AND word, never colour alone. */
export const varianceText = (v: number, measure: Measure) => `${signedMeasure(v, measure)} ${aboveBelow(v)}`;

/** Visual style of each root-cause group. `className` paints HTML bars and swatches. */
export const CAUSE_GROUP_STYLE: Record<string, { label: string; color: string; className: string }> = {
  controllable: { label: "Controlável", color: IBCS.controllable, className: "bg-[#3483fa]" },
  inherent: { label: "Inerente", color: IBCS.inherent, className: "bg-[#a3a8bf]" },
  unexplained: {
    label: "Sem causa identificada",
    color: "#c3c8d9",
    className: "ibcs-hatch-light border border-[#c3c8d9]",
  },
};
export const CAUSE_GROUP_ORDER = ["controllable", "inherent", "unexplained"] as const;

/** Probability of reaching the reference → dot colour (the number is always shown next to it). */
export const probColor = (p: number) =>
  p >= 0.65 ? STATUS.good : p >= 0.35 ? STATUS.warning : STATUS.critical;

/* ------------------------------------------------------------------ numbers */

const nf = (v: number, digits: number) =>
  v.toLocaleString("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits });

/** Short axis/bar label without currency: "8,1 mi" · "650 mil" · "1.234". */
export function shortNumber(v: number): string {
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e9) return `${sign}${nf(a / 1e9, 1)} bi`;
  if (a >= 1e6) return `${sign}${nf(a / 1e6, 1)} mi`;
  if (a >= 1e4) return `${sign}${nf(a / 1e3, 0)} mil`;
  return `${sign}${nf(a, 0)}`;
}

/** Short label with an explicit sign: "+1,2 mi" · "-650 mil". */
export const shortSigned = (v: number) => (v > 0 ? `+${shortNumber(v)}` : shortNumber(v));

/** Escapes text placed in ECharts HTML tooltips. */
export const escapeHtml = (s: string) =>
  s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

/* ------------------------------------------------------------------- bridge */

export interface BridgeBar extends BridgeStep {
  /** Running level where the bar starts (0 for totals). */
  start: number;
  /** Running level where the bar ends (= value for totals). */
  end: number;
}

export interface BridgeLayout {
  bars: BridgeBar[];
  /** True when the totals are cut (axis starts at `base`, not at zero). */
  scaleBreak: boolean;
  /** Value-axis start; 0 without a scale break. */
  base: number;
}

/**
 * Waterfall geometry. Totals and subtotals reset the running level; deltas move it.
 * A scale break is applied when every level is positive and the smallest total is at least
 * `SCALE_BREAK_RATIO` times the largest step, so the steps stay readable.
 */
export function bridgeLayout(steps: BridgeStep[]): BridgeLayout {
  let level = 0;
  const bars: BridgeBar[] = steps.map((s) => {
    if (s.kind === "delta") {
      const start = level;
      level += s.value;
      return { ...s, start, end: level };
    }
    level = s.value;
    return { ...s, start: 0, end: s.value };
  });
  const totals = bars.filter((b) => b.kind !== "delta").map((b) => Math.abs(b.value));
  const deltas = bars.filter((b) => b.kind === "delta").map((b) => Math.abs(b.value));
  if (!totals.length || !deltas.length) return { bars, scaleBreak: false, base: 0 };
  const minTotal = Math.min(...totals);
  const maxDelta = Math.max(...deltas);
  const levels = bars.flatMap((b) => (b.kind === "delta" ? [b.start, b.end] : [b.end]));
  const lo = Math.min(...levels);
  const hi = Math.max(...levels);
  const wanted = maxDelta > 0 && lo > 0 && minTotal >= SCALE_BREAK_RATIO * maxDelta;
  if (!wanted) return { bars, scaleBreak: false, base: 0 };
  // Leave the totals a visible stub about as tall as the steps' range.
  const span = Math.max(hi - lo, maxDelta);
  const base = lo - span * 1.2;
  return base > 0 ? { bars, scaleBreak: true, base } : { bars, scaleBreak: false, base: 0 };
}

/* ------------------------------------------------------------------- layout */

/** Splits rows into the first `max` (shown) and the rest (to fold into "Demais"). */
export function capCategories<T>(rows: T[], max = MAX_CATEGORIES): { shown: T[]; rest: T[] } {
  return { shown: rows.slice(0, max), rest: rows.slice(max) };
}

/**
 * Width of an element in px (0 until measured; jsdom never measures).
 * `ref` is a callback ref: when the element is unmounted and mounted again (the "Ver tabela"
 * toggle swaps the chart for a table), the new element is observed, so the width stays live.
 */
export function useElementWidth<T extends HTMLElement>() {
  const [el, setEl] = useState<T | null>(null);
  const [width, setWidth] = useState(0);
  const ref = useCallback((node: T | null) => setEl(node), []);
  useEffect(() => {
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 0;
      if (w > 0) setWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [el]);
  return { ref, width };
}
