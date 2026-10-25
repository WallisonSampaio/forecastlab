import clsx from "clsx";
import { AlertTriangle, Inbox, Loader2, X } from "lucide-react";
import { useEffect, type ReactNode } from "react";

import { BIAS_STYLE, CLASS_STYLE, CONFIDENCE_STYLE } from "../lib/colors";

export function Card({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={clsx("card min-w-0", className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-4 px-5 pt-4">
          <div className="min-w-0">
            {title && <h3 className="text-[15px] font-semibold text-ink">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={clsx("px-5 pb-5", title || actions ? "pt-3" : "pt-5", bodyClassName)}>{children}</div>
    </section>
  );
}

/** Icon badge colors for KPI cards (brand blue/navy/yellow + status tints). */
const KPI_TONES = {
  blue: "bg-[#eaf2ff] text-brand",
  navy: "bg-[#e8e9f4] text-navy",
  yellow: "bg-[#fff6b3] text-navy",
  green: "bg-emerald-50 text-emerald-700",
  red: "bg-red-50 text-red-700",
  orange: "bg-orange-50 text-orange-700",
} as const;
export type KpiTone = keyof typeof KPI_TONES;

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
  tone?: KpiTone;
}) {
  return (
    <div className="card flex items-start gap-3.5 px-4 py-4 transition-shadow hover:shadow-md">
      {icon && (
        <div
          aria-hidden
          className={clsx(
            "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl [&>svg]:h-[22px] [&>svg]:w-[22px]",
            KPI_TONES[tone],
          )}
        >
          {icon}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium text-muted">{label}</div>
        <div className="mt-0.5 whitespace-nowrap text-[22px] font-semibold leading-tight tracking-tight text-ink 2xl:text-[24px]">
          {value}
        </div>
        {(delta || hint) && (
          <div className="mt-1 flex flex-wrap items-center gap-x-2 text-xs">
            {delta && (
              <span
                className={clsx(
                  "font-medium",
                  deltaTone === "good" && "text-emerald-700",
                  deltaTone === "bad" && "text-red-700",
                  deltaTone === "neutral" && "text-ink-2",
                )}
              >
                {delta}
              </span>
            )}
            {hint && <span className="text-muted">{hint}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

export function Badge({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold",
        className ?? "bg-slate-100 text-ink-2",
      )}
    >
      {children}
    </span>
  );
}

export function ClassBadge({ value, large }: { value?: string | null; large?: boolean }) {
  if (!value) return <Badge>—</Badge>;
  const s = CLASS_STYLE[value] ?? { bg: "bg-slate-100", text: "text-ink-2", icon: "", label: value };
  return (
    <Badge className={clsx(s.bg, s.text, large && "px-3 py-1 text-sm")}>
      <span aria-hidden>{s.icon}</span> {value}
    </Badge>
  );
}

export function BiasBadge({ value }: { value?: string | null }) {
  if (!value) return <Badge>—</Badge>;
  const s = BIAS_STYLE[value];
  return (
    <Badge className={clsx(s?.bg, s?.text)}>
      <span aria-hidden>{s?.icon}</span> {s?.label ?? value}
    </Badge>
  );
}

export function ConfidenceBadge({ value }: { value?: string | null }) {
  if (!value) return <Badge>—</Badge>;
  const s = CONFIDENCE_STYLE[value];
  return <Badge className={clsx(s?.bg, s?.text)}>{value}</Badge>;
}

const SEVERITY: Record<string, string> = {
  critical: "bg-red-100 text-red-800",
  high: "bg-orange-100 text-orange-800",
  medium: "bg-amber-50 text-amber-800",
  low: "bg-slate-100 text-slate-700",
};
export function SeverityBadge({ value }: { value: string }) {
  return <Badge className={SEVERITY[value]}>{value.toUpperCase()}</Badge>;
}

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
    <div className="inline-flex rounded-lg border border-line bg-slate-50 p-0.5" role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={clsx(
            "rounded-md font-medium transition",
            size === "sm" ? "px-3 py-1.5 text-sm" : "px-2 py-1 text-xs",
            value === o.value ? "bg-white text-ink shadow-sm" : "text-muted hover:text-ink",
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
    <div className="flex gap-1 border-b border-line">
      {tabs.map((t) => (
        <button
          key={t.value}
          type="button"
          onClick={() => onChange(t.value)}
          className={clsx(
            "-mb-px inline-flex items-center gap-2 border-b-2 px-3 py-2.5 text-sm font-medium transition",
            value === t.value ? "border-brand text-ink" : "border-transparent text-muted hover:text-ink",
          )}
        >
          {t.icon}
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
  eyebrow,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  eyebrow?: string;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <div className="label-xs mb-1 text-brand">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Loader({ label = "Loading…", className }: { label?: string; className?: string }) {
  return (
    <div className={clsx("flex items-center justify-center gap-2 py-10 text-sm text-muted", className)}>
      <Loader2 size={16} className="animate-spin" /> {label}
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
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <div className="rounded-full bg-slate-100 p-3 text-muted">{icon ?? <Inbox size={20} />}</div>
      <div className="text-sm font-semibold text-ink">{title}</div>
      {children && <div className="max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}

export function ErrorState({ error }: { error: Error | null | undefined }) {
  if (!error) return null;
  return (
    <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
      <AlertTriangle size={16} className="mt-0.5 shrink-0" />
      <span>{error.message}</span>
    </div>
  );
}

export function ProgressBar({ value, className }: { value: number; className?: string }) {
  return (
    <div className={clsx("h-1.5 w-full overflow-hidden rounded-full bg-slate-200", className)}>
      <div
        className="h-full rounded-full bg-brand transition-all duration-500"
        style={{ width: `${Math.max(2, Math.min(100, value * 100))}%` }}
      />
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
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={clsx("card max-h-[90vh] w-full overflow-auto", width)}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <h3 className="font-semibold">{title}</h3>
          <button type="button" className="btn-ghost px-2 py-1" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold text-ink-2">{label}</span>
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
