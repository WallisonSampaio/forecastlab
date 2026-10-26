/** Small building blocks shared by the deep-dive panels (skeletons, chips, action buttons). */
import clsx from "clsx";
import { Info } from "lucide-react";
import type { ReactNode } from "react";

import type { ActionSpec, Tag } from "../../types/deviations";
import { ACTION_ICON } from "./actions";

/** Loading block at the panel's final height (spec §2.0 rule 7). */
export function Skeleton({ height, className }: { height: number; className?: string }) {
  return (
    <div
      aria-hidden
      className={clsx("w-full animate-pulse rounded-2xl bg-[#eef1fa]", className)}
      style={{ height }}
    />
  );
}

/** Tag chip that wraps instead of overflowing. */
export function TagChip({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "brand" }) {
  return (
    <span
      className={clsx(
        "inline-block max-w-full break-words rounded-full px-2.5 py-0.5 text-[11px] font-semibold leading-snug",
        tone === "brand" ? "bg-[#eaf2ff] text-[#1d3f8f]" : "bg-[#eef1fa] text-ink-2",
      )}
    >
      {children}
    </span>
  );
}

export function TagChips({ tags, max = 2 }: { tags: Tag[] | null | undefined; max?: number }) {
  const shown = (tags ?? []).slice(0, max);
  if (!shown.length) return <span className="text-muted">—</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {shown.map((t) => (
        <TagChip key={t.code}>{t.label}</TagChip>
      ))}
    </span>
  );
}

/** Notices of the current cut (derived/partial plan, backtest coverage, period reset…). */
export function NoticeChips({ notices }: { notices: string[] }) {
  if (!notices.length) return null;
  return (
    <ul aria-label="Avisos sobre os dados" className="flex flex-wrap gap-2">
      {notices.map((n) => (
        <li
          key={n}
          className="inline-flex max-w-full items-start gap-1.5 rounded-xl bg-[#fff6dc] px-3 py-1.5 text-[12px] font-medium leading-snug text-[#7a5200]"
        >
          <Info size={14} aria-hidden className="mt-px shrink-0" />
          <span className="min-w-0 break-words">{n}</span>
        </li>
      ))}
    </ul>
  );
}

/** One button per backend action ("Perguntar à IA", "Simular cenário", …). */
export function ActionButtons({
  actions,
  onRun,
  variant = "chip",
}: {
  actions: ActionSpec[];
  onRun: (a: ActionSpec) => void;
  /** chip: small rounded chips (panels); bar: regular buttons (drawer action bar). */
  variant?: "chip" | "bar";
}) {
  if (!actions.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {actions.map((a, i) => {
        const Icon = ACTION_ICON[a.kind];
        return (
          <button
            key={`${a.kind}-${i}`}
            type="button"
            onClick={() => onRun(a)}
            className={clsx(
              variant === "chip"
                ? "inline-flex items-center gap-1.5 rounded-full border border-line bg-white/90 px-3 py-1.5 text-[12.5px] font-semibold text-ink shadow-[0_2px_8px_-4px_rgba(45,50,119,0.18)] transition hover:border-[#c9dcff] hover:bg-[#f4f8ff]"
                : i === 0
                  ? "btn-primary px-3.5 py-2 text-[13px]"
                  : "btn-secondary px-3.5 py-2 text-[13px]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            )}
          >
            {Icon && <Icon size={14} aria-hidden className="shrink-0" />}
            {a.label}
          </button>
        );
      })}
    </div>
  );
}
