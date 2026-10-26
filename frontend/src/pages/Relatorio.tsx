import clsx from "clsx";
import { BookOpenText, FileWarning, Presentation, RotateCw, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { JourneyGate } from "../components/journey/JourneyGate";
import { RerunBanner } from "../components/journey/RerunBanner";
import { ExportMenu } from "../components/RunControls";
import { ChapterFrame } from "../components/story/ChapterFrame";
import { ChapterRail } from "../components/story/ChapterRail";
import { chapterHref } from "../components/story/helpers";
import { ScopeChip, ScopeSelect } from "../components/story/ScopeSelect";
import { Card, EmptyState, ErrorState } from "../components/ui";
import { useGet } from "../hooks/useApi";
import { useFilters } from "../hooks/useFilters";
import { isJourneyReady, useJourney } from "../hooks/useJourney";
import { usePresentationMode } from "../hooks/usePresentationMode";
import type { ChapterId } from "../lib/deviationsUrl";
import {
  chapterOrDefault,
  reportScopeFromSearch,
  ROUTES,
  saveReportScope,
  type ReportScope,
} from "../lib/routes";
import type { Story } from "../types/story";

export const STORY_PATH = "/api/story";

/** Keys that move between chapters (spec §2.2.1, "Keyboard"). */
const NAV_KEYS: Record<string, "prev" | "next" | "first" | "last"> = {
  ArrowLeft: "prev",
  PageUp: "prev",
  ArrowRight: "next",
  PageDown: "next",
  Home: "first",
  End: "last",
};

/** Keys are ignored while typing or choosing in a form control, and inside dialogs. */
function isFormTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  if (target.closest('[role="dialog"]')) return true;
  return ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName);
}

const pulse = "animate-pulse rounded-2xl bg-[#eef1fa]";

/** Frame skeleton at the final heights (spec §2.0, rule 7). */
function ReportSkeleton() {
  return (
    <div aria-busy="true" aria-label="Carregando o relatório">
      <div className={clsx(pulse, "mb-7 h-[52px]")} />
      <div className={clsx(pulse, "h-3 w-56")} />
      <div className={clsx(pulse, "mt-3 h-8 w-[min(100%,720px)]")} />
      <div className={clsx(pulse, "mt-2 h-8 w-[min(100%,520px)]")} />
      <div className={clsx(pulse, "mt-4 h-4 w-[min(100%,420px)]")} />
      <div className="mt-7 grid gap-6 xl:grid-cols-12">
        <div className={clsx(pulse, "h-[400px] rounded-3xl xl:col-span-8")} />
        <div className={clsx(pulse, "h-[400px] rounded-3xl xl:col-span-4")} />
      </div>
    </div>
  );
}

/**
 * Stage 2 · Relatório executivo (`/app/relatorio/:capitulo`, spec §2.2).
 *
 * - One `GET /api/story?{scope}` brings every chapter, so changing chapters makes no request.
 * - The chapter lives in the URL path (replace); the scope in the query (region | channel | category),
 *   mirrored to `useFilters` and saved for the session when the user picks it.
 * - ←/→, PageUp/PageDown, Home/End move between chapters; `P` toggles presentation mode.
 */
export default function Relatorio() {
  const { capitulo } = useParams();
  const chapterId = chapterOrDefault(capitulo);
  const [searchParams] = useSearchParams();
  const search = searchParams.toString();
  // Stable while the query string is unchanged (it is the story's query key and an effect dependency).
  const scope = useMemo<ReportScope>(() => reportScopeFromSearch(new URLSearchParams(search)), [search]);
  const navigate = useNavigate();
  const presentation = usePresentationMode();
  const presenting = presentation.active;
  const setFilters = useFilters((s) => s.setFilters);

  const journey = useJourney();
  const ready = isJourneyReady(journey.data) || journey.isError;
  const story = useGet<Story>(STORY_PATH, scope, { staleTime: 60_000, enabled: ready });
  const data = story.data;
  const chapters = useMemo(() => (data?.available ? (data.chapters ?? []) : []), [data]);
  const pos = Math.max(
    0,
    chapters.findIndex((c) => c.id === chapterId),
  );
  const chapter = chapters[pos];

  // The session remembers the scope on screen (the sidebar link reopens the report with it).
  useEffect(() => {
    saveReportScope(scope);
  }, [scope]);

  const goTo = useCallback(
    (id: ChapterId) => {
      if (id !== chapterId) navigate(chapterHref(id, scope, presenting), { replace: true });
    },
    [chapterId, navigate, scope, presenting],
  );

  const changeScope = useCallback(
    (next: ReportScope) => {
      setFilters({ ...next });
      saveReportScope(next);
      navigate(chapterHref(chapterId, next, presenting));
    },
    [chapterId, navigate, presenting, setFilters],
  );

  const askAi = useCallback(
    (question: string) => {
      setFilters({ ...scope });
      navigate(ROUTES.ia(question));
    },
    [navigate, scope, setFilters],
  );

  // Keyboard: ←/→ PageUp/PageDown Home/End between chapters; P toggles presentation (spec §2.2.1).
  const togglePresentation = presentation.toggle;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || isFormTarget(e.target)) return;
      if (!chapters.length) return;
      if (e.key === "p" || e.key === "P") {
        e.preventDefault();
        togglePresentation();
        return;
      }
      const move = NAV_KEYS[e.key];
      if (!move || e.shiftKey) return;
      const target =
        move === "first" ? 0 : move === "last" ? chapters.length - 1 : move === "prev" ? pos - 1 : pos + 1;
      if (target < 0 || target >= chapters.length) return;
      e.preventDefault();
      goTo(chapters[target].id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [chapters, pos, goTo, togglePresentation]);

  // A new chapter starts at its top (the rail stays mounted and sticky). When the control that moved
  // the story was inside the old chapter (footer links), focus goes to the new H1, not to the page.
  const lastChapter = useRef(chapterId);
  useEffect(() => {
    if (lastChapter.current === chapterId) return;
    lastChapter.current = chapterId;
    if (window.scrollY > 0) window.scrollTo({ top: 0 });
    const active = document.activeElement;
    if (!active || active === document.body) {
      document.getElementById(`capitulo-${chapterId}`)?.focus({ preventScroll: true });
    }
  }, [chapterId]);

  if (journey.data && !isJourneyReady(journey.data)) {
    return <JourneyGate journey={journey.data} />;
  }

  const reference = data?.available ? data.reference : null;
  const eyebrow = `Etapa 2 de 3 · Relatório executivo${
    reference?.cycle_label ? ` · Ciclo S&OP ${reference.cycle_label}` : ""
  }`;

  let content;
  if (story.error && !data) {
    content = (
      <Card>
        <div className="space-y-4">
          <ErrorState error={story.error} />
          <button type="button" className="btn-secondary" onClick={() => story.refetch()}>
            <RotateCw size={15} aria-hidden /> Tentar novamente
          </button>
        </div>
      </Card>
    );
  } else if (!data) {
    content = <ReportSkeleton />;
  } else if (!data.available || !chapter) {
    content = (
      <Card>
        <EmptyState title="Relatório indisponível" icon={<FileWarning />}>
          {data.reason ?? "Não há dados suficientes para montar o relatório neste escopo."}
        </EmptyState>
      </Card>
    );
  } else {
    content = (
      <div className={clsx("transition-opacity", story.isPlaceholderData && "opacity-60")}>
        <ChapterRail
          chapters={chapters}
          currentId={chapter.id}
          hrefOf={(id) => chapterHref(id, scope, presenting)}
          presenting={presenting}
        />
        <ChapterFrame
          key={chapter.id}
          story={data}
          chapter={chapter}
          scope={scope}
          presenting={presenting}
          onAskAi={askAi}
          onOpenMember={(href) => navigate(href)}
        />
      </div>
    );
  }

  return (
    <div className={clsx(presenting && "mx-auto max-w-[1280px]")} data-relatorio>
      <RerunBanner journey={journey.data} className="mb-4" />
      {/* Compact header (not a big PageHeader): the chapter H1 is the page's headline. */}
      <header className="mb-6 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-white/80 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.12em] text-brand shadow-[0_4px_12px_-6px_rgba(52,131,250,0.5)]">
            <BookOpenText size={14} aria-hidden className="shrink-0" />
            <span className="break-words">{eyebrow}</span>
          </div>
          <ScopeChip value={scope} onClear={() => changeScope({})} />
          {!presenting && (
            <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
              <ScopeSelect value={scope} onChange={changeScope} />
              <ExportMenu scope={scope} />
              <button
                type="button"
                className="btn-secondary"
                onClick={presentation.enter}
                title="Apresentar (tecla P)"
                aria-keyshortcuts="P"
              >
                <Presentation size={15} aria-hidden /> Apresentar
              </button>
            </div>
          )}
        </div>
        {reference?.plan_derived && (
          <div
            data-plan-derived
            className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-amber-50 px-3 py-1 text-[12px] font-semibold text-amber-800"
          >
            <TriangleAlert size={13} aria-hidden className="shrink-0" />
            <span className="break-words">
              Orçamento estimado automaticamente — desvios vs orçamento são ilustrativos.
            </span>
          </div>
        )}
      </header>
      {content}
    </div>
  );
}
