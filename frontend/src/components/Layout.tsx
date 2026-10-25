import clsx from "clsx";
import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  Database,
  Gauge,
  Layers,
  LayoutDashboard,
  Linkedin,
  LineChart,
  Settings,
  SplitSquareHorizontal,
  Target,
} from "lucide-react";
import { Suspense } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

import { useGet, useJob } from "../hooks/useApi";
import { BRAND } from "../lib/branding";
import type { DatasetInfo } from "../types";
import { Loader, ProgressBar } from "./ui";

const NAV = [
  { to: "/app/overview", label: "Overview", icon: LayoutDashboard },
  { to: "/app/data", label: "Data", icon: Database },
  { to: "/app/forecasting", label: "Forecasting", icon: LineChart },
  { to: "/app/models", label: "Model Performance", icon: BarChart3 },
  { to: "/app/scenarios", label: "Scenarios", icon: SplitSquareHorizontal },
  { to: "/app/sop", label: "S&OP", icon: Target },
  { to: "/app/fva", label: "FVA", icon: Gauge },
  { to: "/app/ai", label: "AI Analyst", icon: Bot },
  { to: "/app/alerts", label: "Alert Center", icon: Bell },
  { to: "/app/settings", label: "Settings", icon: Settings },
];

export function Logo({ dark = false, size = 30 }: { dark?: boolean; size?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <img src="/favicon.svg" alt="" width={size} height={size} className="rounded-lg" />
      <span className={clsx("text-[17px] font-semibold tracking-tight", dark ? "text-white" : "text-ink")}>
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
        title={BRAND.titleEn}
      >
        <span>
          Developed by <span className="font-semibold text-ink-2 group-hover:text-brand">{BRAND.author}</span>
        </span>
        <Linkedin size={13} className="text-[#0a66c2]" />
      </a>
    );
  }
  if (variant === "footer") {
    return (
      <div className="text-center text-xs text-muted">
        <div>
          <span className="font-semibold text-ink-2">{BRAND.signatureEn}</span> · {BRAND.titleEn}
        </div>
        <a
          href={BRAND.linkedin}
          target="_blank"
          rel="noreferrer"
          className="mt-0.5 inline-flex items-center gap-1 text-brand hover:underline"
        >
          <Linkedin size={12} /> {BRAND.linkedinLabel}
        </a>
      </div>
    );
  }
  return (
    <a
      href={BRAND.linkedin}
      target="_blank"
      rel="noreferrer"
      className="block rounded-lg border border-white/15 bg-white/5 p-3 text-[11px] leading-snug text-blue-100/80 transition hover:border-white/30 hover:bg-white/10"
    >
      <div className="text-blue-200/70">Developed by</div>
      <div className="mt-0.5 text-[13px] font-semibold text-white">{BRAND.author}</div>
      <div className="mt-1">{BRAND.titleEn}</div>
      <div className="mt-2 inline-flex items-center gap-1 text-[#70b5f9]">
        <Linkedin size={12} /> LinkedIn
      </div>
    </a>
  );
}

function RunStatus() {
  const { data: job } = useJob();
  if (!job) return null;
  return (
    <div className="flex min-w-[260px] items-center gap-3 rounded-lg border border-blue-200 bg-white px-3 py-1.5">
      <Activity size={14} className="animate-pulse text-brand" />
      <div className="min-w-0 flex-1">
        <div className="flex justify-between text-[11px] font-medium text-navy">
          <span>Forecast run {job.run_id}</span>
          <span>{Math.round(job.progress * 100)}%</span>
        </div>
        <ProgressBar value={job.progress} className="mt-1 bg-blue-100" />
      </div>
    </div>
  );
}

function Topbar() {
  const { data: ds } = useGet<DatasetInfo>("/api/data/active", undefined, {
    retry: false,
    staleTime: 30_000,
  });
  const { data: alerts } = useGet<{ summary: { by_severity: Record<string, number> } }>(
    "/api/alerts",
    undefined,
    {
      retry: false,
      staleTime: 60_000,
    },
  );
  const urgent = (alerts?.summary.by_severity.critical ?? 0) + (alerts?.summary.by_severity.high ?? 0);
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-4 bg-sun-soft px-6 shadow-[0_1px_0_rgba(0,0,0,0.08)]">
      <div className="flex min-w-0 items-center gap-2 text-xs text-muted">
        <Layers size={14} />
        {ds ? (
          <span className="truncate">
            <span className="font-medium text-ink-2">{ds.dataset_version}</span> · {ds.name} · run{" "}
            <span className="font-medium text-ink-2">{ds.active_run ?? "—"}</span>
          </span>
        ) : (
          <span>No dataset loaded</span>
        )}
      </div>
      <div className="ml-auto flex items-center gap-4">
        <RunStatus />
        <Link
          to="/app/alerts"
          className="relative rounded-lg p-2 text-ink-2 hover:bg-slate-100"
          aria-label="Alerts"
        >
          <Bell size={18} />
          {urgent > 0 && (
            <span className="absolute -right-0.5 -top-0.5 rounded-full bg-red-600 px-1.5 text-[10px] font-semibold text-white">
              {urgent}
            </span>
          )}
        </Link>
        <Signature variant="inline" />
      </div>
    </header>
  );
}

export function AppLayout() {
  const location = useLocation();
  return (
    <div className="flex min-h-full">
      <aside className="fixed inset-y-0 left-0 z-40 flex w-[244px] flex-col bg-sidebar px-4 py-5">
        <Link to="/" className="px-2">
          <Logo dark />
        </Link>
        <div className="mt-1 px-2 text-[11px] text-blue-200/70">AI Demand Planning & S&OP</div>
        <nav className="mt-7 flex flex-col gap-0.5">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] font-medium transition",
                  isActive
                    ? "bg-sun font-semibold text-navy"
                    : "text-blue-100/85 hover:bg-white/10 hover:text-white",
                )
              }
            >
              <Icon size={17} strokeWidth={1.8} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto">
          <Signature />
        </div>
      </aside>
      <div className="ml-[244px] flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main key={location.pathname} className="mx-auto w-full max-w-[1600px] flex-1 px-6 py-6">
          <Suspense fallback={<Loader />}>
            <Outlet />
          </Suspense>
        </main>
        <footer className="border-t border-line bg-white px-6 py-4">
          <Signature variant="footer" />
        </footer>
      </div>
    </div>
  );
}
