import clsx from "clsx";
import { ArrowLeft, ArrowRight, Info, ScanSearch, Sparkles, Upload } from "lucide-react";
import { Link } from "react-router-dom";

import type { ChapterId, DeviationUrlState } from "../../lib/deviationsUrl";
import { ROUTES, type ReportScope } from "../../lib/routes";
import type { Chapter, Story } from "../../types/story";
import { Card } from "../ui";
import { ChapterVisual } from "./chapterVisuals";
import { chapterHref, deepDiveHref, disclosureText } from "./helpers";
import { Scqa, Storyline } from "./Storyline";
import { Takeaways } from "./Takeaways";

export interface ChapterFrameProps {
  story: Story;
  chapter: Chapter;
  scope: ReportScope;
  presenting?: boolean;
  /** "Perguntar à IA": mirrors the report scope to the tools' filters, then opens the AI analyst. */
  onAskAi: (question: string) => void;
  /** A member clicked in the chapter visual (variance_bars) opens in the deep dive. */
  onOpenMember: (href: string) => void;
}

/** Notice of a chapter without data (spec §2.2.1 states): the backend text plus where to fix it. */
function NoticeCard({ notice }: { notice: string | null }) {
  return (
    <Card>
      <div className="flex flex-wrap items-start gap-4">
        <span
          aria-hidden
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-50 text-amber-700"
        >
          <Info size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="break-words text-[14.5px] leading-relaxed text-ink" data-chapter-notice>
            {notice ?? "Este capítulo não tem dados nesta base."}
          </p>
          <Link to={ROUTES.entrada({ acao: "carregar" })} className="btn-secondary mt-4">
            <Upload size={15} aria-hidden /> Carregar nova base
          </Link>
        </div>
      </div>
    </Card>
  );
}

/**
 * One chapter of the executive report (spec §2.2.1): eyebrow, statement H1, question and context line,
 * the body (visual 8/12 + "Leituras" 4/12; Resumo and Decisões full width), the footer navigation and
 * the disclosure line.
 */
export function ChapterFrame({
  story,
  chapter,
  scope,
  presenting = false,
  onAskAi,
  onOpenMember,
}: ChapterFrameProps) {
  const chapters = story.chapters;
  const total = chapters.length;
  const pos = Math.max(
    0,
    chapters.findIndex((c) => c.id === chapter.id),
  );
  const n = pos + 1;
  const prev = pos > 0 ? chapters[pos - 1] : null;
  const next = pos < total - 1 ? chapters[pos + 1] : null;
  const isLast = !next;
  const empty = chapter.status === "empty";
  const kind = chapter.visual.kind;
  const ref = story.reference;

  const hrefOf = (id: ChapterId) => chapterHref(id, scope, presenting);
  const takeawayHref = (params: Partial<DeviationUrlState>) => deepDiveHref(params, scope, chapter.id);
  const investigateHref = chapter.investigate
    ? deepDiveHref(chapter.investigate.params, scope, chapter.id)
    : null;
  // Last chapter: "Próximo" becomes "Investigar os desvios →", the journey's way into stage 3: the deep
  // dive's default view with the report scope (spec §2.2.1). It replaces the chapter's own "Investigar"
  // button there, so the footer never offers two doors to the same page.
  const exitHref = deepDiveHref({}, scope, chapter.id);

  const headline = empty
    ? chapter.title
    : kind === "kpis"
      ? story.governing_thought || chapter.headline
      : chapter.headline;

  const openMember = (level: string, member: string) =>
    onOpenMember(
      deepDiveHref(
        { ...(chapter.investigate?.params ?? {}), nivel: level as DeviationUrlState["nivel"], sel: member },
        scope,
        chapter.id,
      ),
    );

  const visual = (
    <ChapterVisual chapter={chapter} horizonMonths={ref.horizon_months} onOpenMember={openMember} />
  );

  let body;
  if (empty) {
    body = <NoticeCard notice={chapter.notice} />;
  } else if (kind === "kpis") {
    body = (
      <div className="space-y-7">
        <Scqa scqa={story.scqa} />
        {visual}
        <Storyline chapters={chapters.slice(pos + 1)} startAt={n + 1} hrefOf={hrefOf} />
      </div>
    );
  } else if (kind === "decision_table") {
    body = (
      <div className="space-y-6">
        <div>
          {visual}
          <p className="mt-3 text-[12px] leading-relaxed text-muted">
            Regras determinísticas sobre desvios, viabilidade, erro e ajustes — nenhum número é gerado por IA.
          </p>
        </div>
        {chapter.takeaways.length > 0 && <Takeaways items={chapter.takeaways} hrefOf={takeawayHref} />}
      </div>
    );
  } else if (chapter.takeaways.length === 0) {
    body = visual;
  } else {
    body = (
      <div className="grid gap-6 xl:grid-cols-12">
        <div className="min-w-0 xl:col-span-8">{visual}</div>
        <Takeaways items={chapter.takeaways} hrefOf={takeawayHref} className="xl:col-span-4" />
      </div>
    );
  }

  return (
    <article aria-labelledby={`capitulo-${chapter.id}`} data-chapter-frame={chapter.id}>
      <header>
        <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-brand">
          Capítulo {n} de {total} · {chapter.title}
        </p>
        {/* Measured with Inter bold on the demo headlines (≤ 170 characters): 26 px from ~1530 px wide,
            easing to ~24,5 px at 1440 and ~23 px at 1366, keeps every H1 on 2 lines (QA §6.2 #4);
            68ch ≈ 1190 px caps the measure on wide screens. Presentation: 28 px in the 1280 px column. */}
        <h1
          id={`capitulo-${chapter.id}`}
          tabIndex={-1}
          className={clsx(
            "mt-2 max-w-[68ch] break-words font-bold leading-snug tracking-tight text-ink outline-none",
            presenting ? "text-[28px]" : "text-[clamp(22px,1.7vw,26px)]",
          )}
        >
          {headline}
        </h1>
        <p className="mt-3 max-w-[90ch] text-[15px] leading-relaxed text-ink-2">{chapter.question}</p>
        {chapter.context && (
          <p className="mt-1 max-w-[110ch] break-words text-[12.5px] leading-relaxed text-muted">
            {chapter.context}
          </p>
        )}
      </header>

      <div className="mt-7">{body}</div>

      <nav
        aria-label="Navegação do capítulo"
        className="mt-9 flex flex-wrap items-center gap-3 border-t border-line pt-5"
      >
        {prev && (
          <Link to={hrefOf(prev.id)} replace className="btn-ghost">
            <ArrowLeft size={16} aria-hidden /> {prev.short}
          </Link>
        )}
        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
          {chapter.ask_ai && (
            <button type="button" className="btn-ghost" onClick={() => onAskAi(chapter.ask_ai as string)}>
              <Sparkles size={16} className="text-brand" aria-hidden /> Perguntar à IA
            </button>
          )}
          {chapter.secondary_action && (
            <Link to={chapter.secondary_action.route} className="btn-secondary">
              {chapter.secondary_action.label}
            </Link>
          )}
          {investigateHref && !isLast && (
            <Link to={investigateHref} className="btn-primary">
              <ScanSearch size={16} aria-hidden /> Investigar no deep dive
            </Link>
          )}
          {next ? (
            <Link to={hrefOf(next.id)} replace className="btn-secondary">
              Próximo: {next.title} <ArrowRight size={16} aria-hidden />
            </Link>
          ) : (
            <Link to={exitHref} className="btn-primary">
              Investigar os desvios <ArrowRight size={16} aria-hidden />
            </Link>
          )}
        </div>
      </nav>

      <p className="mt-5 break-words text-[11px] leading-relaxed text-muted" data-disclosure>
        {disclosureText(ref)}
      </p>
    </article>
  );
}

export default ChapterFrame;
