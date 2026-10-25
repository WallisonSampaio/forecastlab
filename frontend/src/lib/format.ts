/** Number formatting helpers (compact, executive-friendly). */

export type Measure = "units" | "revenue";
export type ValueFormat = "currency" | "units" | "percent" | "percent_signed" | "number" | "text" | "measure";

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function compact(v: number | null | undefined, digits = 1): string {
  if (!isNum(v)) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e9) return `${sign}${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}${(a / 1e6).toFixed(2)}M`;
  if (a >= 1e4) return `${sign}${(a / 1e3).toFixed(digits)}K`;
  return `${sign}${a.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

export const money = (v: number | null | undefined) => (isNum(v) ? `R$ ${compact(v)}` : "—");
export const units = (v: number | null | undefined) => (isNum(v) ? compact(v) : "—");

export function pct(v: number | null | undefined, digits = 1, signed = false): string {
  if (!isNum(v)) return "—";
  const s = (v * 100).toFixed(digits);
  return signed && v > 0 ? `+${s}%` : `${s}%`;
}

export const full = (v: number | null | undefined, digits = 0) =>
  isNum(v)
    ? v.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits })
    : "—";

export function formatValue(
  v: unknown,
  format: ValueFormat | string | undefined,
  measure: Measure = "units",
): string {
  if (v === null || v === undefined) return "—";
  switch (format) {
    case "currency":
      return money(v as number);
    case "units":
      return units(v as number);
    case "percent":
      return pct(v as number);
    case "percent_signed":
      return pct(v as number, 1, true);
    case "number":
      return isNum(v) ? (Number.isInteger(v) ? full(v) : full(v, 2)) : String(v);
    case "measure":
      return measure === "revenue" ? money(v as number) : units(v as number);
    default:
      return typeof v === "number" ? full(v, 2) : String(v);
  }
}

export const fmtMeasure = (v: number | null | undefined, m: Measure) =>
  m === "revenue" ? money(v) : units(v);

export function monthLabel(iso: string | null | undefined, style: "short" | "long" = "short"): string {
  if (!iso) return "—";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return d.toLocaleDateString("en-US", { month: style === "short" ? "short" : "long", year: "numeric" });
}

export const shortMonth = (iso: string) => {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return `${d.toLocaleDateString("en-US", { month: "short" })} ${String(d.getFullYear()).slice(2)}`;
};
