/** Small building blocks shared by the three Entrada step cards (spec §2.1). */
import clsx from "clsx";
import { ChevronDown, CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

/** "Ver detalhes" / "Recolher" toggle in a step card header. */
export function ToggleButton({
  open,
  onToggle,
  controls,
  closedLabel = "Ver detalhes",
}: {
  open: boolean;
  onToggle: () => void;
  controls: string;
  closedLabel?: string;
}) {
  return (
    <button
      type="button"
      aria-expanded={open}
      aria-controls={controls}
      onClick={onToggle}
      className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-[12.5px] font-semibold text-ink-2 transition hover:bg-[#eef1fa] hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
    >
      {open ? "Recolher" : closedLabel}
      <ChevronDown size={15} aria-hidden className={clsx("transition-transform", open && "rotate-180")} />
    </button>
  );
}

/** Loading block at its final height (spec §2.0, rule 7). */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={clsx("animate-pulse rounded-2xl bg-[#eef1fa]", className)} />;
}

export type NoticeTone = "good" | "warn" | "bad" | "info";

const NOTICE: Record<NoticeTone, { box: string; icon: string; Icon: typeof Info }> = {
  good: {
    box: "bg-emerald-50/80 ring-emerald-100 text-emerald-900",
    icon: "text-emerald-600",
    Icon: CircleCheck,
  },
  warn: {
    box: "bg-amber-50/80 ring-amber-200/70 text-amber-900",
    icon: "text-amber-600",
    Icon: TriangleAlert,
  },
  bad: { box: "bg-red-50/90 ring-red-100 text-red-900", icon: "text-red-600", Icon: CircleAlert },
  info: { box: "bg-[#eef5ff] ring-[#d6e6ff] text-[#1f4f9e]", icon: "text-brand", Icon: Info },
};

/** Tinted surface + icon + words (never a coloured side stripe, spec §2.0 rule 5). */
export function Notice({
  tone,
  title,
  children,
  role,
  className,
  "data-testid": testId,
}: {
  tone: NoticeTone;
  title: ReactNode;
  children?: ReactNode;
  role?: "status" | "alert";
  className?: string;
  "data-testid"?: string;
}) {
  const s = NOTICE[tone];
  return (
    <div
      role={role}
      data-testid={testId}
      className={clsx("rounded-2xl px-4 py-3.5 text-sm ring-1", s.box, className)}
    >
      <div className="flex items-start gap-2.5">
        <s.Icon size={18} aria-hidden className={clsx("mt-px shrink-0", s.icon)} />
        <div className="min-w-0 flex-1">
          <p className="break-words font-semibold leading-snug">{title}</p>
          {children && <div className="mt-2 text-[13px] leading-relaxed">{children}</div>}
        </div>
      </div>
    </div>
  );
}
