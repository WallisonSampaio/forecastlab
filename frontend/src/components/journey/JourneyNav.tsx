import clsx from "clsx";
import {
  BarChart3,
  Bell,
  Bot,
  ChevronDown,
  CircleAlert,
  CircleCheck,
  Database,
  LineChart,
  Loader2,
  Lock,
  SplitSquareHorizontal,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";

import { useGet } from "../../hooks/useApi";
import { runProgressPct, useJourney } from "../../hooks/useJourney";
import { TONES, type Tone } from "../../lib/colors";
import { isReportPath, loadReportScope, reportScopeFromSearch, ROUTES } from "../../lib/routes";
import type { JourneyStatus } from "../../types/journey";

/** localStorage key of the Governança group state ("1" open, "0" collapsed). */
export const GOV_STORAGE_KEY = "fl.nav.gov";
export const LOCKED_HINT = "Disponível após a competição de modelos";
/** "1 crítico ou alto" / "3 críticos ou altos" (sidebar alerts badge; the topbar bell has its own copy). */
const urgentAlertsText = (n: number) => `${n} ${n === 1 ? "crítico ou alto" : "críticos ou altos"}`;
const LOCKED_HINT_ID = "nav-journey-locked-hint";

type LinkItem = { to: string; label: string; icon: typeof Bell; tone: Tone };

const TOOLS: LinkItem[] = [
  { to: "/app/forecasting", label: "Workspace de forecast", icon: LineChart, tone: "purple" },
  { to: "/app/scenarios", label: "Cenários e metas", icon: SplitSquareHorizontal, tone: "green" },
  { to: "/app/alerts", label: "Alertas", icon: Bell, tone: "red" },
  { to: "/app/ai", label: "Analista de IA", icon: Bot, tone: "navy" },
];

const GOVERNANCE: LinkItem[] = [
  { to: "/app/models", label: "Modelos e FVA", icon: BarChart3, tone: "orange" },
  { to: "/app/data", label: "Bases de dados", icon: Database, tone: "teal" },
];

const ACTIVE =
  "bg-gradient-to-r from-[#3483fa] to-[#5b9cff] text-white shadow-[0_10px_20px_-10px_rgba(52,131,250,0.9)]";
const IDLE = "text-ink-2 hover:bg-white hover:shadow-[0_6px_14px_-10px_rgba(45,50,119,0.4)]";

const startsWith = (pathname: string, base: string) => pathname === base || pathname.startsWith(`${base}/`);

function readGovOpen(): boolean {
  try {
    return localStorage.getItem(GOV_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeGovOpen(open: boolean) {
  try {
    localStorage.setItem(GOV_STORAGE_KEY, open ? "1" : "0");
  } catch {
    /* storage unavailable: the group just does not remember its state */
  }
}

/* ------------------------------------------------------------------------------ groups */

function GroupHeader({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div id={id} className="px-2.5 pb-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-muted">
      {children}
    </div>
  );
}

/** Tool / governance link: lighter than the journey (13 px, 28 px tile). */
function ToolLink({ item, extra }: { item: LinkItem; extra?: ReactNode }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      className={({ isActive }) =>
        clsx(
          "flex items-center gap-2.5 rounded-xl px-2.5 py-1.5 text-[13px] font-medium leading-snug transition",
          isActive ? ACTIVE : IDLE,
        )
      }
    >
      {({ isActive }) => (
        <>
          <span
            aria-hidden
            className={clsx(
              "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg transition",
              isActive ? "bg-white/20 text-white" : TONES[item.tone].soft,
            )}
          >
            <Icon size={15} strokeWidth={2} />
          </span>
          <span className="min-w-0 flex-1 break-words">{item.label}</span>
          {extra}
        </>
      )}
    </NavLink>
  );
}

/* ------------------------------------------------------------------------------ journey */

type StepStatus = { kind: "done" | "running" | "attention" | "locked"; text: string; pct?: number };

function entradaStatus(j: JourneyStatus | undefined): StepStatus | null {
  if (!j) return null;
  if (j.run.state === "running") {
    const pct = runProgressPct(j.run.progress);
    return { kind: "running", pct, text: `Competição de modelos em andamento: ${pct}%` };
  }
  if (j.stage === "pronto") return { kind: "done", text: "Etapa concluída" };
  if (j.run.state === "failed") return { kind: "attention", text: "A última execução falhou" };
  if (j.stage === "dados") return { kind: "attention", text: "Carregue uma base para começar" };
  return { kind: "attention", text: "Falta rodar a competição de modelos" };
}

function StatusIcon({ status, active }: { status: StepStatus; active: boolean }) {
  if (status.kind === "running") {
    return (
      <span
        aria-hidden
        className={clsx(
          "inline-flex shrink-0 items-center gap-1 text-[11px] font-semibold tabular-nums",
          active ? "text-white" : "text-brand",
        )}
      >
        <Loader2 size={14} className="animate-spin" />
        {status.pct}%
      </span>
    );
  }
  const Icon = status.kind === "done" ? CircleCheck : status.kind === "locked" ? Lock : CircleAlert;
  const color = active
    ? "text-white"
    : status.kind === "done"
      ? "text-emerald-600"
      : status.kind === "locked"
        ? "text-muted"
        : "text-amber-500";
  return <Icon aria-hidden size={15} strokeWidth={2.2} className={clsx("shrink-0", color)} />;
}

function JourneyLink({
  step,
  to,
  title,
  sub,
  active,
  status,
}: {
  step: number;
  to: string;
  title: string;
  sub?: string;
  active: boolean;
  status: StepStatus | null;
}) {
  const statusId = `nav-journey-status-${step}`;
  const locked = status?.kind === "locked";
  const describedBy = locked ? LOCKED_HINT_ID : status ? statusId : undefined;
  return (
    <li>
      <Link
        to={to}
        aria-current={active ? "page" : undefined}
        aria-describedby={describedBy}
        title={locked ? LOCKED_HINT : undefined}
        data-locked={locked || undefined}
        className={clsx(
          "flex items-center gap-2.5 rounded-2xl px-2.5 py-2 text-[14px] font-semibold leading-snug transition",
          active ? ACTIVE : IDLE,
        )}
      >
        <span
          aria-hidden
          className={clsx(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-[13px] font-bold tabular-nums transition",
            active ? "bg-white/20 text-white" : locked ? "bg-[#eef1fa] text-muted" : TONES.blue.soft,
          )}
        >
          {step}
        </span>
        <span className={clsx("min-w-0 flex-1 break-words", locked && !active && "text-muted")}>
          {title}
          {sub && (
            <>
              <span className="sr-only"> · </span>
              <span className="block text-[11.5px] font-medium opacity-80">{sub}</span>
            </>
          )}
        </span>
        {status && <StatusIcon status={status} active={active} />}
      </Link>
      {/* Outside the link, so the status describes it without changing its accessible name. */}
      {status && !locked && (
        <span id={statusId} className="sr-only">
          {status.text}
        </span>
      )}
    </li>
  );
}

/**
 * Sidebar navigation (spec §1.2): JORNADA (3 numbered steps with status), FERRAMENTAS (4 tools) and
 * GOVERNANÇA (2 links, collapsible, state in localStorage "fl.nav.gov"). Locked steps stay links: the
 * page itself renders `JourneyGate`.
 */
export function JourneyNav() {
  const { pathname, search } = useLocation();
  // On the report the URL is the scope's source of truth (§1.4); elsewhere, the session's last scope.
  const reportScope = isReportPath(pathname)
    ? reportScopeFromSearch(new URLSearchParams(search))
    : loadReportScope();
  const { data: journey } = useJourney();
  const { data: alerts } = useGet<{ summary: { by_severity: Record<string, number> } }>(
    "/api/alerts",
    undefined,
    { retry: false, staleTime: 60_000 },
  );
  const urgent = (alerts?.summary.by_severity.critical ?? 0) + (alerts?.summary.by_severity.high ?? 0);

  const [govOpen, setGovOpen] = useState(readGovOpen);
  const inGovernance = GOVERNANCE.some((g) => startsWith(pathname, g.to));
  // Entering a governance page shows its link (not persisted: the stored choice still applies elsewhere).
  useEffect(() => {
    if (inGovernance) setGovOpen(true);
  }, [inGovernance]);
  const toggleGov = () => {
    const next = !govOpen;
    setGovOpen(next);
    writeGovOpen(next);
  };

  const locked: StepStatus | null =
    journey && journey.stage !== "pronto" ? { kind: "locked", text: LOCKED_HINT } : null;

  return (
    <nav aria-label="Navegação principal" className="mt-5 flex flex-col gap-4">
      <div role="group" aria-labelledby="nav-g-jornada">
        <GroupHeader id="nav-g-jornada">Jornada</GroupHeader>
        <ol className="flex flex-col gap-1">
          <JourneyLink
            step={1}
            to={ROUTES.entrada()}
            title="Entrada"
            sub="dados e modelos"
            active={startsWith(pathname, "/app/entrada")}
            status={entradaStatus(journey)}
          />
          <JourneyLink
            step={2}
            to={ROUTES.relatorio("resumo", reportScope)}
            title="Relatório executivo"
            active={startsWith(pathname, "/app/relatorio")}
            status={locked}
          />
          <JourneyLink
            step={3}
            to={ROUTES.desvios({})}
            title="Desvios"
            active={startsWith(pathname, "/app/desvios")}
            status={locked}
          />
        </ol>
        <span id={LOCKED_HINT_ID} className="sr-only">
          {LOCKED_HINT}
        </span>
      </div>

      <div role="group" aria-labelledby="nav-g-ferramentas">
        <GroupHeader id="nav-g-ferramentas">Ferramentas</GroupHeader>
        <div className="flex flex-col gap-0.5">
          {TOOLS.map((item) => (
            <ToolLink
              key={item.to}
              item={item}
              extra={
                item.to === "/app/alerts" && urgent > 0 ? (
                  <span className="shrink-0 rounded-full bg-red-100 px-1.5 py-0.5 text-[10.5px] font-bold tabular-nums text-red-700">
                    <span aria-hidden>{urgent}</span>
                    <span className="sr-only"> {urgentAlertsText(urgent)}</span>
                  </span>
                ) : undefined
              }
            />
          ))}
        </div>
      </div>

      <div role="group" aria-labelledby="nav-g-governanca">
        <button
          type="button"
          id="nav-g-governanca"
          aria-expanded={govOpen}
          aria-controls="nav-governanca-links"
          onClick={toggleGov}
          className="flex w-full items-center justify-between rounded-lg px-2.5 pb-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-muted transition hover:text-ink-2"
        >
          Governança
          <ChevronDown
            aria-hidden
            size={14}
            className={clsx("transition-transform", govOpen ? "rotate-0" : "-rotate-90")}
          />
        </button>
        <div
          id="nav-governanca-links"
          hidden={!govOpen}
          className={govOpen ? "flex flex-col gap-0.5" : "hidden"}
        >
          {GOVERNANCE.map((item) => (
            <ToolLink key={item.to} item={item} />
          ))}
        </div>
      </div>
    </nav>
  );
}

export default JourneyNav;
