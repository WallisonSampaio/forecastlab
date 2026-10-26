import clsx from "clsx";
import {
  AlertTriangle,
  ArrowDown,
  ArrowDownRight,
  ArrowDownToLine,
  ArrowUp,
  ArrowUpRight,
  ChartColumn,
  Check,
  CircleCheck,
  Inbox,
  Loader2,
  Minus,
  OctagonAlert,
  Table2,
  TriangleAlert,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState, type HTMLAttributes, type ReactNode } from "react";

import { BIAS_STYLE, CLASS_STYLE, CONFIDENCE_STYLE, TONES, type Tone } from "../lib/colors";
import { t } from "../lib/labels";

/* ------------------------------------------------------------------ icon tile */
/** Glossy "3D" gradient tile that carries an icon (premium soft-UI look). */
export function IconTile({
  icon,
  tone = "blue",
  size = "md",
  className,
}: {
  icon: ReactNode;
  tone?: Tone;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const dims = {
    sm: "h-9 w-9 rounded-xl [&>svg]:h-[18px] [&>svg]:w-[18px]",
    md: "h-11 w-11 rounded-2xl [&>svg]:h-[22px] [&>svg]:w-[22px]",
    lg: "h-14 w-14 rounded-2xl [&>svg]:h-[26px] [&>svg]:w-[26px]",
  }[size];
  return (
    <div
      aria-hidden
      className={clsx(
        "relative flex shrink-0 items-center justify-center overflow-hidden bg-gradient-to-br text-white",
        dims,
        TONES[tone].tile,
        className,
      )}
    >
      <span className="pointer-events-none absolute inset-x-1 top-0.5 h-1/2 rounded-[inherit] bg-gradient-to-b from-white/45 to-white/0" />
      <span className="relative drop-shadow-[0_1px_1px_rgba(0,0,0,0.18)] [&>svg]:h-[inherit] [&>svg]:w-[inherit]">
        {icon}
      </span>
    </div>
  );
}

/* ----------------------------------------------------------------------- card */
/**
 * Other DOM attributes (`data-visual`, `data-question`, `id`, `aria-*`…) are forwarded to the
 * `<section>`, so a journey visual block is `<Card data-visual="onde" data-question="Onde está o
 * desvio?">` (spec §2.0, rule 1).
 */
export function Card({
  title,
  subtitle,
  actions,
  icon,
  tone = "blue",
  children,
  className,
  bodyClassName,
  ...rest
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  icon?: ReactNode;
  tone?: Tone;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
} & Omit<HTMLAttributes<HTMLElement>, "title" | "children" | "className">) {
  return (
    <section {...rest} className={clsx("card min-w-0", className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-4 px-6 pt-5">
          <div className="flex min-w-0 items-center gap-3">
            {icon && <IconTile icon={icon} tone={tone} size="sm" />}
            <div className="min-w-0">
              {title && <h3 className="text-[15px] font-semibold tracking-tight text-ink">{title}</h3>}
              {subtitle && <p className="mt-0.5 text-xs leading-relaxed text-muted">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={clsx("px-6 pb-6", title || actions ? "pt-4" : "pt-6", bodyClassName)}>{children}</div>
    </section>
  );
}

/* ------------------------------------------------------------------ KPI card */
export function DeltaPill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "good" | "bad" | "neutral";
}) {
  const Icon = tone === "good" ? ArrowUpRight : tone === "bad" ? ArrowDownRight : Minus;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-0.5 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold",
        tone === "good" && "bg-emerald-100/80 text-emerald-700",
        tone === "bad" && "bg-red-100/80 text-red-700",
        tone === "neutral" && "bg-slate-100 text-ink-2",
      )}
    >
      <Icon size={12} strokeWidth={2.5} />
      {children}
    </span>
  );
}

/**
 * KPI tile: pastel tinted surface + optional 3D icon tile + large value.
 * Nothing is cut off: the value stays on one line and the label wraps freely.
 */
export function KpiCard({
  label,
  value,
  delta,
  deltaTone = "neutral",
  hint,
  icon,
  tone = "blue",
}: {
  label: string;
  value: ReactNode;
  delta?: ReactNode;
  deltaTone?: "good" | "bad" | "neutral";
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: Tone;
}) {
  return (
    <div
      data-kpi=""
      className={clsx(
        "card flex min-w-0 items-center gap-4 bg-gradient-to-br px-5 py-5 transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_18px_36px_-16px_rgba(45,50,119,0.3)]",
        TONES[tone].surface,
      )}
    >
      {icon && <IconTile icon={icon} tone={tone} size="lg" />}
      <div className="min-w-0 flex-1">
        <div className="break-words text-[13px] font-medium leading-snug text-ink-2">{label}</div>
        <div className="mt-1 whitespace-nowrap text-[clamp(1.3rem,1.55vw,1.7rem)] font-bold leading-tight tracking-tight text-ink">
          {value}
        </div>
        {(delta || hint) && (
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11.5px] leading-snug">
            {delta && <DeltaPill tone={deltaTone}>{delta}</DeltaPill>}
            {hint && <span className="text-muted">{hint}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------- badges */
export function Badge({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold",
        className ?? "bg-slate-100 text-ink-2",
      )}
    >
      {children}
    </span>
  );
}

/** Icon of each target-feasibility class (icon + label, never colour alone; no emoji). */
const CLASS_ICON: Record<string, LucideIcon> = {
  REALISTIC: CircleCheck,
  STRETCH: TriangleAlert,
  AGGRESSIVE: OctagonAlert,
  UNDERESTIMATED: ArrowDownToLine,
};

/** Icon of each bias class. */
const BIAS_ICON: Record<string, LucideIcon> = { Over: ArrowUp, Under: ArrowDown, Balanced: Check };

export function ClassBadge({ value, large }: { value?: string | null; large?: boolean }) {
  if (!value) return <Badge>—</Badge>;
  const s = CLASS_STYLE[value] ?? { bg: "bg-slate-100", text: "text-ink-2", label: value };
  const Icon = CLASS_ICON[value];
  return (
    <Badge className={clsx(s.bg, s.text, large && "px-3.5 py-1 text-sm")}>
      {Icon && <Icon aria-hidden size={large ? 15 : 12} strokeWidth={2.4} className="shrink-0" />}
      {s.label}
    </Badge>
  );
}

export function BiasBadge({ value }: { value?: string | null }) {
  if (!value) return <Badge>—</Badge>;
  const s = BIAS_STYLE[value];
  const Icon = BIAS_ICON[value];
  return (
    <Badge className={clsx(s?.bg, s?.text)}>
      {Icon && <Icon aria-hidden size={12} strokeWidth={2.4} className="shrink-0" />}
      {s?.label ?? value}
    </Badge>
  );
}

export function ConfidenceBadge({ value }: { value?: string | null }) {
  if (!value) return <Badge>—</Badge>;
  const s = CONFIDENCE_STYLE[value];
  return <Badge className={clsx(s?.bg, s?.text)}>{s?.label ?? value}</Badge>;
}

const SEVERITY: Record<string, string> = {
  critical: "bg-red-100 text-red-800",
  high: "bg-orange-100 text-orange-800",
  medium: "bg-amber-100/70 text-amber-800",
  low: "bg-slate-100 text-slate-700",
};
export function SeverityBadge({ value }: { value: string }) {
  return <Badge className={SEVERITY[value]}>{t.severity(value)}</Badge>;
}

/* ------------------------------------------------------------ toggles & tabs */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  size = "sm",
}: {
  value: T;
  options: { value: T; label: ReactNode }[];
  onChange: (v: T) => void;
  size?: "sm" | "xs";
}) {
  return (
    <div className="inline-flex rounded-xl bg-[#eef1fa] p-1" role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={clsx(
            "whitespace-nowrap rounded-lg font-semibold transition",
            size === "sm" ? "px-3.5 py-1.5 text-sm" : "px-2.5 py-1 text-xs",
            value === o.value
              ? "bg-white text-ink shadow-[0_4px_10px_-4px_rgba(45,50,119,0.3)]"
              : "text-muted hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Tabs<T extends string>({
  value,
  tabs,
  onChange,
}: {
  value: T;
  tabs: { value: T; label: ReactNode; icon?: ReactNode }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex max-w-full flex-wrap gap-1 rounded-2xl border border-white/80 bg-white/70 p-1.5 shadow-[0_6px_20px_-12px_rgba(45,50,119,0.25)] backdrop-blur">
      {tabs.map((tb) => (
        <button
          key={tb.value}
          type="button"
          aria-pressed={value === tb.value}
          onClick={() => onChange(tb.value)}
          className={clsx(
            "inline-flex items-center gap-2 whitespace-nowrap rounded-xl px-4 py-2 text-sm font-semibold transition",
            value === tb.value
              ? "bg-gradient-to-r from-[#3483fa] to-[#5b9cff] text-white shadow-[0_8px_18px_-8px_rgba(52,131,250,0.8)]"
              : "text-ink-2 hover:bg-white",
          )}
        >
          {tb.icon}
          {tb.label}
        </button>
      ))}
    </div>
  );
}

/* --------------------------------------------------------------- page header */
export function PageHeader({
  title,
  subtitle,
  actions,
  eyebrow,
  icon,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  eyebrow?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && (
          <div className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-white/80 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.12em] text-brand shadow-[0_4px_12px_-6px_rgba(52,131,250,0.5)] [&>svg]:h-3.5 [&>svg]:w-3.5">
            {icon}
            {eyebrow}
          </div>
        )}
        <h1 className="text-[28px] font-bold leading-tight tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/* --------------------------------------------------------------- feedback UI */
export function Loader({ label = "Carregando…", className }: { label?: string; className?: string }) {
  return (
    <div className={clsx("flex items-center justify-center gap-2 py-12 text-sm text-muted", className)}>
      <Loader2 size={16} className="animate-spin text-brand" /> {label}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  icon,
}: {
  title: string;
  children?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-14 text-center">
      <IconTile icon={icon ?? <Inbox />} tone="blue" size="lg" />
      <div className="text-base font-semibold text-ink">{title}</div>
      {children && <div className="max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}

export function ErrorState({ error }: { error: Error | null | undefined }) {
  if (!error) return null;
  return (
    <div className="flex items-start gap-2 rounded-2xl border border-red-200 bg-red-50/90 px-4 py-3 text-sm text-red-800">
      <AlertTriangle size={16} className="mt-0.5 shrink-0" />
      <span>{error.message}</span>
    </div>
  );
}

export function ProgressBar({
  value,
  className,
  color,
}: {
  value: number;
  className?: string;
  color?: string;
}) {
  return (
    <div className={clsx("h-2 w-full overflow-hidden rounded-full bg-[#e9edf8]", className)}>
      <div
        className={clsx(
          "h-full rounded-full transition-all duration-500",
          !color && "bg-gradient-to-r from-[#3483fa] to-[#7db4ff]",
        )}
        style={{ width: `${Math.max(2, Math.min(100, value * 100))}%`, background: color }}
      />
    </div>
  );
}

/** Circular progress (probability, quality score…). */
export function ProgressRing({
  value,
  size = 120,
  stroke = 11,
  color = "#3483fa",
  children,
}: {
  value: number;
  size?: number;
  stroke?: number;
  color?: string;
  children?: ReactNode;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, value));
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="#eaeef9" strokeWidth={stroke} fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={color}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${c * v} ${c}`}
          style={{ filter: `drop-shadow(0 4px 6px ${color}55)`, transition: "stroke-dasharray .6s" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">{children}</div>
    </div>
  );
}

export function Modal({
  open,
  title,
  onClose,
  children,
  width = "max-w-xl",
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  width?: string;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  // Keyboard users land inside the dialog (also when it opens from the series drawer) and go
  // back to the button that opened it when it closes.
  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const el = dialogRef.current;
    if (el && !el.contains(document.activeElement)) el.focus();
    return () => {
      if (opener && opener.isConnected) opener.focus();
    };
  }, [open]);
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#1b1f3b]/30 p-4 backdrop-blur-sm"
      onMouseDown={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={clsx("card max-h-[90vh] w-full overflow-auto bg-white outline-none", width)}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-6 py-4">
          <h3 className="text-base font-semibold">{title}</h3>
          <button type="button" className="btn-ghost px-2 py-1" onClick={onClose} aria-label="Fechar">
            <X size={16} />
          </button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------- chart frame */
export interface ChartTableColumn {
  label: string;
  align?: "left" | "right";
}

export interface ChartTableRow {
  key: string;
  cells: ReactNode[];
}

/**
 * Wraps a chart with the "Ver tabela" toggle (spec §2.0 chart declutter): the table renders the
 * same data points, one row each. `legend` is an optional inline key (scenario notation, hints);
 * `note` is a muted caption under the chart or table.
 */
export function ChartFrame({
  ariaLabel,
  columns,
  rows,
  legend,
  note,
  children,
  className,
}: {
  ariaLabel: string;
  columns: ChartTableColumn[];
  rows: ChartTableRow[];
  legend?: ReactNode;
  note?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <figure className={clsx("min-w-0", className)}>
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] leading-snug text-ink-2">
          {legend}
        </div>
        <button
          type="button"
          aria-pressed={asTable}
          aria-label={`${asTable ? "Ver gráfico" : "Ver tabela"}: ${ariaLabel}`}
          onClick={() => setAsTable((v) => !v)}
          className="ml-auto inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1 text-[12px] font-semibold text-ink-2 transition hover:bg-[#eef1fa] hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        >
          {asTable ? <ChartColumn size={14} aria-hidden /> : <Table2 size={14} aria-hidden />}
          {asTable ? "Ver gráfico" : "Ver tabela"}
        </button>
      </div>
      {asTable ? (
        <div className="overflow-auto rounded-2xl border border-line bg-white/70">
          <table className="table-base tabular">
            <caption className="sr-only">{ariaLabel}</caption>
            <thead>
              <tr>
                {columns.map((c, i) => (
                  <th key={i} scope="col" className={clsx(c.align === "right" && "text-right")}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  {r.cells.map((cell, i) => (
                    <td
                      key={i}
                      className={clsx(
                        columns[i]?.align === "right" ? "text-right" : "whitespace-normal break-words",
                      )}
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        children
      )}
      {note && <figcaption className="mt-2 text-[11px] leading-relaxed text-muted">{note}</figcaption>}
    </figure>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold text-ink-2">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div>
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-0.5 text-lg font-semibold text-ink">{value}</div>
      {sub && <div className="text-xs text-muted">{sub}</div>}
    </div>
  );
}
