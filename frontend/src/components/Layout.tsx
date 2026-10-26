import clsx from "clsx";
import { Activity, Bell, Linkedin, Sparkles, Star, X } from "lucide-react";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useGet, useJob } from "../hooks/useApi";
import { usePresentationMode } from "../hooks/usePresentationMode";
import { BRAND } from "../lib/branding";
import { ROUTES, sectionKey } from "../lib/routes";
import { JourneyNav } from "./journey/JourneyNav";
import { IconTile, Loader, ProgressBar } from "./ui";

/** "1 crítico ou alto" / "3 críticos ou altos" (topbar bell). */
const urgentAlertsText = (n: number) => `${n} ${n === 1 ? "crítico ou alto" : "críticos ou altos"}`;

const CLIENT_LOGO = import.meta.env.VITE_CLIENT_LOGO_URL;
const CLIENT_NAME = import.meta.env.VITE_CLIENT_NAME ?? "Cliente";

/**
 * Optional white-label logo for private demos. The file lives in
 * frontend/public/brand/ (git-ignored) and is enabled with VITE_CLIENT_LOGO_URL,
 * so third-party trademarks never reach the public repository.
 */
export function ClientLogo({ variant = "sidebar" }: { variant?: "sidebar" | "inline" }) {
  const [missing, setMissing] = useState(false);
  if (!CLIENT_LOGO || missing) return null;
  // object-cover on a wide box crops the empty margin of square, padded logo files.
  const img = (cls: string) => (
    <img src={CLIENT_LOGO} alt={CLIENT_NAME} onError={() => setMissing(true)} className={cls} />
  );
  if (variant === "inline") {
    return (
      <span className="inline-flex items-center gap-3">
        <span className="h-7 w-px bg-white/30" aria-hidden />
        <span className="rounded-xl bg-white px-2 py-1">{img("h-9 w-[132px] object-cover")}</span>
      </span>
    );
  }
  return (
    <div className="mt-4 flex items-center gap-2 rounded-2xl border border-line bg-white px-3 py-1.5">
      <span className="whitespace-nowrap text-[10px] font-bold uppercase tracking-wider text-muted">
        Preparado para
      </span>
      {img("ml-auto h-9 w-[112px] object-cover")}
    </div>
  );
}

export function Logo({ dark = false, size = 34 }: { dark?: boolean; size?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <img
        src="/favicon.svg"
        alt=""
        width={size}
        height={size}
        className="rounded-xl shadow-[0_8px_16px_-6px_rgba(45,50,119,0.6)]"
      />
      <span className={clsx("text-[18px] font-bold tracking-tight", dark ? "text-white" : "text-ink")}>
        Forecast<span className={dark ? "text-sun" : "text-brand"}>Lab</span>
      </span>
    </span>
  );
}

export function Signature({ variant = "sidebar" }: { variant?: "sidebar" | "inline" | "footer" }) {
  if (variant === "inline") {
    return (
      <a
        href={BRAND.linkedin}
        target="_blank"
        rel="noreferrer"
        className="group inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink"
        title={BRAND.titlePt}
      >
        <span>
          Desenvolvido por{" "}
          <span className="font-semibold text-ink-2 group-hover:text-brand">{BRAND.author}</span>
        </span>
        <Linkedin size={13} className="text-[#0a66c2]" />
      </a>
    );
  }
  if (variant === "footer") {
    return (
      <div className="text-center text-xs text-muted">
        <span className="font-semibold text-ink-2">{BRAND.signaturePt}</span> · {BRAND.titlePt} ·{" "}
        <a
          href={BRAND.linkedin}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 font-medium text-brand hover:underline"
        >
          <Linkedin size={12} /> {BRAND.linkedinLabel}
        </a>
      </div>
    );
  }
  // Sidebar promo-style author card. The star sits beside the name (not above it) so the whole sidebar,
  // Governança collapsed, fits a 768 px-high screen without scrolling (spec §6.2, item 3).
  return (
    <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#2d3277] via-[#3a4bb5] to-[#3483fa] p-4 text-white shadow-[0_16px_30px_-14px_rgba(45,50,119,0.8)]">
      <div className="pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full bg-white/10" />
      <div className="relative flex items-center gap-3">
        <IconTile icon={<Star fill="currentColor" />} tone="yellow" size="sm" />
        <div className="min-w-0">
          <div className="text-[11px] font-medium text-blue-100/90">Desenvolvido por</div>
          <div className="text-[15px] font-bold leading-tight">{BRAND.author}</div>
        </div>
      </div>
      <div className="relative mt-2 text-[11px] leading-snug text-blue-100/85">{BRAND.titlePt}</div>
      <a
        href={BRAND.linkedin}
        target="_blank"
        rel="noreferrer"
        className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-xl bg-sun px-3 py-2 text-xs font-bold text-navy shadow-[0_8px_16px_-8px_rgba(255,214,0,0.9)] transition hover:brightness-105"
      >
        <Linkedin size={13} /> Ver LinkedIn
      </a>
    </div>
  );
}

function RunStatus() {
  const { data: job } = useJob();
  if (!job) return null;
  return (
    <div className="hidden min-w-[240px] items-center gap-3 rounded-2xl border border-white/80 bg-white/85 px-3 py-2 shadow-sm lg:flex">
      <Activity size={15} className="animate-pulse text-brand" />
      <div className="min-w-0 flex-1">
        <div className="flex justify-between text-[11px] font-semibold text-navy">
          <span>Forecast em execução</span>
          <span>{Math.round(job.progress * 100)}%</span>
        </div>
        <ProgressBar value={job.progress} className="mt-1" />
      </div>
    </div>
  );
}

function AskBar() {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const question = q.trim();
    if (!question) return;
    nav(ROUTES.ia(question));
    setQ("");
  };
  return (
    <form onSubmit={submit} className="relative w-full max-w-xl">
      <Sparkles size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-brand" />
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        aria-label="Pergunte ao analista de IA"
        placeholder="Pergunte à IA… ex.: a meta de dezembro é realista?"
        className="w-full rounded-2xl border border-white/80 bg-white/85 py-3 pl-11 pr-4 text-sm text-ink shadow-[0_8px_24px_-14px_rgba(45,50,119,0.35)] outline-none backdrop-blur transition placeholder:text-muted focus:border-brand/40 focus:ring-4 focus:ring-brand/10"
      />
    </form>
  );
}

/**
 * AskBar, run status, alerts bell and author link. The dataset/run chip was removed (spec §1.2): its
 * information lives in the Entrada summary line.
 */
function Topbar() {
  // Same query key as the sidebar badge (JourneyNav), so both share one request.
  const { data: alerts } = useGet<{ summary: { by_severity: Record<string, number> } }>(
    "/api/alerts",
    undefined,
    { retry: false, staleTime: 60_000 },
  );
  const urgent = (alerts?.summary.by_severity.critical ?? 0) + (alerts?.summary.by_severity.high ?? 0);
  return (
    <header className="sticky top-0 z-30 flex items-center gap-4 px-6 pb-3 pt-4 backdrop-blur-md [background:linear-gradient(180deg,rgba(243,245,252,0.92),rgba(243,245,252,0.6))]">
      <AskBar />
      <div className="ml-auto flex items-center gap-3">
        <RunStatus />
        <Link
          to={ROUTES.alertas()}
          className="relative flex h-11 w-11 items-center justify-center rounded-2xl border border-white/80 bg-white/85 text-ink-2 shadow-sm transition hover:text-brand"
          aria-label={urgent > 0 ? `Alertas: ${urgentAlertsText(urgent)}` : "Alertas"}
        >
          <Bell size={18} />
          {urgent > 0 && (
            <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-gradient-to-br from-[#ff7a7a] to-[#ef4444] px-1 text-[10px] font-bold text-white shadow">
              {urgent}
            </span>
          )}
        </Link>
        <a
          href={BRAND.linkedin}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-2.5 rounded-2xl border border-white/80 bg-white/85 py-1.5 pl-1.5 pr-3 shadow-sm transition hover:bg-white"
          title={BRAND.titlePt}
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-[#3483fa] to-[#2d3277] text-xs font-bold text-white">
            WS
          </span>
          <span className="hidden leading-tight md:block">
            <span className="block text-[13px] font-semibold text-ink">{BRAND.author}</span>
            <span className="block text-[11px] text-muted">Data & AI · Supply Chain</span>
          </span>
        </a>
      </div>
    </header>
  );
}

/**
 * App shell: sidebar (journey + tools + governance, signature card at the bottom), topbar, page, footer.
 *
 * - `<main>` is keyed by the first two path segments, so moving between report chapters
 *   (`/app/relatorio/:capitulo`) keeps the report mounted (spec §1.2).
 * - Presentation mode (`?apresentacao=1` on `/app/relatorio/*`, spec §1.6) hides the sidebar, topbar and
 *   footer; Esc or the floating "Sair da apresentação" button leaves it.
 */
export function AppLayout() {
  const location = useLocation();
  const { active: presenting, exit: exitPresentation } = usePresentationMode();

  useEffect(() => {
    if (!presenting) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      // An open dialog consumes Esc first (it closes itself).
      if (document.querySelector('[role="dialog"][aria-modal="true"]')) return;
      exitPresentation();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [presenting, exitPresentation]);

  return (
    <div className="min-h-screen" data-presentation={presenting || undefined}>
      {!presenting && (
        <aside
          aria-label="Menu lateral"
          className="fixed bottom-4 left-4 top-4 z-40 flex w-[252px] flex-col overflow-y-auto rounded-[28px] border border-white/80 bg-white/80 px-4 py-4 shadow-[0_20px_50px_-24px_rgba(45,50,119,0.35)] backdrop-blur-xl"
        >
          <Link to="/" className="px-2">
            <Logo />
          </Link>
          <div className="mt-1.5 px-2 text-[11px] font-medium text-muted">Planejamento de Demanda & S&OP</div>
          <ClientLogo />
          <JourneyNav />
          <div className="mt-auto pt-4">
            <Signature />
          </div>
        </aside>
      )}
      <div className={clsx("flex min-w-0 flex-col", !presenting && "ml-[284px]")}>
        {!presenting && <Topbar />}
        <main
          key={sectionKey(location.pathname)}
          className={clsx("mx-auto w-full max-w-[1680px] flex-1 px-6 pb-8", presenting ? "pt-6" : "pt-3")}
        >
          <Suspense fallback={<Loader />}>
            <Outlet />
          </Suspense>
        </main>
        {!presenting && (
          <footer className="px-6 pb-6">
            <Signature variant="footer" />
          </footer>
        )}
      </div>
      {presenting && (
        <button
          type="button"
          onClick={exitPresentation}
          className="btn-secondary fixed bottom-5 right-5 z-50 shadow-[0_12px_28px_-12px_rgba(45,50,119,0.45)]"
        >
          <X size={15} aria-hidden /> Sair da apresentação
          <kbd
            aria-hidden
            className="ml-1 rounded-md border border-line bg-plane px-1.5 py-0.5 text-[10px] font-semibold text-muted"
          >
            Esc
          </kbd>
        </button>
      )}
    </div>
  );
}
