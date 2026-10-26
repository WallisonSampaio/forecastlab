/** Number & date formatting in Brazilian Portuguese (compact, executive-friendly). */

export type Measure = "units" | "revenue";
export type ValueFormat = "currency" | "units" | "percent" | "percent_signed" | "number" | "text" | "measure";

const LOCALE = "pt-BR";
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const dec = (v: number, digits: number) =>
  v.toLocaleString(LOCALE, { minimumFractionDigits: digits, maximumFractionDigits: digits });

/** 1.234 · 45,6 mil · 12,34 mi · 1,20 bi */
export function compact(v: number | null | undefined, digits = 1): string {
  if (!isNum(v)) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e9) return `${sign}${dec(a / 1e9, 2)} bi`;
  if (a >= 1e6) return `${sign}${dec(a / 1e6, 2)} mi`;
  if (a >= 1e4) return `${sign}${dec(a / 1e3, digits)} mil`;
  return `${sign}${a.toLocaleString(LOCALE, { maximumFractionDigits: 0 })}`;
}

export const money = (v: number | null | undefined) =>
  isNum(v) ? `R$ ${compact(v)}`.replace("R$ -", "-R$ ") : "—";
export const units = (v: number | null | undefined) => (isNum(v) ? compact(v) : "—");

export function pct(v: number | null | undefined, digits = 1, signed = false): string {
  if (!isNum(v)) return "—";
  const s = dec(v * 100, digits);
  return signed && v > 0 ? `+${s}%` : `${s}%`;
}

export const full = (v: number | null | undefined, digits = 0) => (isNum(v) ? dec(v, digits) : "—");

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

export const MONTHS_SHORT = [
  "jan",
  "fev",
  "mar",
  "abr",
  "mai",
  "jun",
  "jul",
  "ago",
  "set",
  "out",
  "nov",
  "dez",
];
export const MONTHS_LONG = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
];

const parts = (iso: string) => ({ y: Number(iso.slice(0, 4)), m: Number(iso.slice(5, 7)) - 1 });

/** "dez/2026" (short) or "dezembro de 2026" (long). */
export function monthLabel(iso: string | null | undefined, style: "short" | "long" = "short"): string {
  if (!iso) return "—";
  const { y, m } = parts(iso);
  return style === "long" ? `${MONTHS_LONG[m]} de ${y}` : `${MONTHS_SHORT[m]}/${y}`;
}

/** "dez/26" — compact axis label. */
export const shortMonth = (iso: string) => {
  const { y, m } = parts(iso);
  return `${MONTHS_SHORT[m]}/${String(y).slice(2)}`;
};

/** Greeting by local time of day. */
export function greeting(date = new Date()): string {
  const h = date.getHours();
  return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
}

/* ------------------------------------------- journey helpers (spec §2.0, rule 6) */

/** Money with an explicit sign: "+R$ 0,42 mi" · "-R$ 4,09 mi" · "R$ 0". */
export const signedMoney = (v: number | null | undefined): string =>
  isNum(v) ? (v > 0 ? `+${money(v)}` : money(v)) : "—";

/** Units with an explicit sign: "+1,2 mil" · "-850". */
export const signedUnits = (v: number | null | undefined): string =>
  isNum(v) ? (v > 0 ? `+${units(v)}` : units(v)) : "—";

/** Signed value in the measure's unit (R$ for revenue, units otherwise). */
export const signedMeasure = (v: number | null | undefined, m: Measure): string =>
  m === "revenue" ? signedMoney(v) : signedUnits(v);

/** "abaixo" for a negative deviation, "acima" otherwise (same rule as the backend `dir_`). */
export const aboveBelow = (v: number): "acima" | "abaixo" => (v < 0 ? "abaixo" : "acima");

/**
 * Percentage points from a fraction: pp(0.125) → "12,5 p.p."; pp(-0.02) → "-2,0 p.p.";
 * pp(0.011, 1, true) → "+1,1 p.p.".
 */
export function pp(v: number | null | undefined, digits = 1, signed = false): string {
  if (!isNum(v)) return "—";
  const x = Math.abs(v * 100) < 0.5 * 10 ** -digits ? 0 : v * 100; // no "-0,0"
  const s = dec(x, digits);
  return `${signed && x > 0 ? "+" : ""}${s} p.p.`;
}

/** Display formats a backend KPI card can ask for (`KpiSpec.format`, spec §4.3.3). */
export type KpiFormat =
  "currency" | "currency_signed" | "units" | "percent" | "percent_signed" | "pp" | "text";

/** KPI ids that carry a probability ("Chance de …"): whole percentages, like the headlines. */
const isProbabilityKpi = (id: string | undefined) => !!id && id.startsWith("prob");

/**
 * Formats a backend KPI card value. `text` (when sent) wins for "text" and for a null value.
 * Probabilities (ids `prob_*`) use 0 decimals, so the card matches its headline ("29% de chance").
 */
export function formatKpi(spec: {
  id?: string;
  value: number | null;
  format: KpiFormat | string;
  text?: string | null;
}): string {
  const { value: v, format, text } = spec;
  if (format === "text") return text ?? (isNum(v) ? full(v) : "—");
  if (!isNum(v)) return text ?? "—";
  switch (format) {
    case "currency":
      return money(v);
    case "currency_signed":
      return signedMoney(v);
    case "units":
      return units(v);
    case "percent":
      return pct(v, isProbabilityKpi(spec.id) ? 0 : 1);
    case "percent_signed":
      return pct(v, 1, true);
    case "pp":
      return pp(v, 1, true);
    default:
      return Number.isInteger(v) ? full(v) : full(v, 2);
  }
}

/** Forecast lead of the backtest: "1–3 meses" (fold horizon 3) · "1 mês" (fold horizon 1). */
export function lagLabel(foldHorizon: number | null | undefined): string {
  const h = isNum(foldHorizon) ? Math.max(1, Math.round(foldHorizon)) : 1;
  return h === 1 ? "1 mês" : `1–${h} meses`;
}
