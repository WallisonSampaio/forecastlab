/**
 * Stage 3 · Desvios — the deviation deep dive (`/app/desvios?…`, spec §2.3).
 *
 * Overview first, then zoom and filter, then details on demand (Shneiderman):
 *   header (headline = the answer) · controls · drill path · notices
 *   KPI strip · ONDE (7/12) | POR QUE (5/12) · QUANDO · exceptions table · "Ficha da série" drawer
 *
 * The URL is the only state (lib/deviationsUrl.ts): a reload or a shared link restores the view.
 * First load = 3 requests (summary, focus, exceptions) besides the journey status.
 * Exactly 5 `data-visual` blocks: kpis, onde, porque, quando, excecoes.
 */
import clsx from "clsx";
import { ArrowLeft, Check, CircleCheck, Link2, RotateCcw, ScanSearch, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";

import { useDimensions } from "../components/FilterBar";
import { OverrideForm } from "../components/OverrideForm";
import { useActionRunner, aiQuestion, type OverrideTarget } from "../components/desvios/actions";
import { Breadcrumb } from "../components/desvios/Breadcrumb";
import { NoticeChips } from "../components/desvios/common";
import { ControlBar } from "../components/desvios/ControlBar";
import { ExceptionsTable } from "../components/desvios/ExceptionsTable";
import { KpiStrip } from "../components/desvios/KpiStrip";
import { SeriesDrawer } from "../components/desvios/SeriesDrawer";
import {
  CHAPTER_SHORT,
  focusFilters,
  useDeviationState,
  type DeviationNav,
  type FocusPayload,
  type SummaryPayload,
} from "../components/desvios/state";
import { WhenPanel } from "../components/desvios/WhenPanel";
import { WherePanel } from "../components/desvios/WherePanel";
import { WhyPanel } from "../components/desvios/WhyPanel";
import { JourneyGate } from "../components/journey/JourneyGate";
import { RerunBanner } from "../components/journey/RerunBanner";
import { EmptyState, ErrorState, Loader, Modal, PageHeader } from "../components/ui";
import { useGet } from "../hooks/useApi";
import { useJourney } from "../hooks/useJourney";
import { LENS_DEFAULT_CMP, LENS_OF, apiParams, toSearchParams, type Cmp } from "../lib/deviationsUrl";
import { ROUTES, loadReportScope } from "../lib/routes";
import { ApiError, type Params } from "../services/api";
import type { JourneyStatus } from "../types/journey";

export const SUMMARY_PATH = "/api/deviations/summary";
export const FOCUS_PATH = "/api/deviations/focus";
export const PERIOD_RESET_NOTICE = "Período fora da janela desta comparação — voltamos ao padrão.";
export const SAVED_NOTICE = "Ajuste salvo — consenso recalculado.";
const SAVED_MS = 4000;

/* --------------------------------------------------------- adjustment modal */

/** "Criar ajuste comercial": `OverrideForm` prefilled from the action (posts /api/overrides). */
function OverrideModal({
  target,
  onClose,
  onSaved,
}: {
  target: OverrideTarget;
  onClose: () => void;
  onSaved: () => void;
}) {
  const dims = useDimensions();
  // Portal + z-[60]: above the series drawer (z-50, also a portal), whatever opened the modal.
  return createPortal(
    <div className="relative z-[60]">
      <Modal open title="Criar ajuste comercial" onClose={onClose} width="max-w-2xl">
        <p className="mb-4 text-sm leading-relaxed text-ink-2">
          <span className="font-semibold text-ink">
            {target.customer}
            {target.sku ? ` · ${target.sku}` : ""}
          </span>{" "}
          — ajuste sugerido pelo deep dive. Revise o mês, o evento e o uplift antes de adicionar; o consenso é
          recalculado ao salvar.
        </p>
        {dims.data ? (
          <OverrideForm
            customer={target.customer}
            sku={target.sku}
            horizon={dims.data.horizon ?? []}
            defaults={target.defaults}
            onSaved={onSaved}
          />
        ) : dims.error ? (
          <ErrorState error={dims.error} />
        ) : (
          <Loader label="Carregando o horizonte…" />
        )}
      </Modal>
    </div>,
    document.body,
  );
}

/* ------------------------------------------------------------------ header */

function CopyLinkButton() {
  const [state, setState] = useState<"ok" | "fail" | null>(null);
  useEffect(() => {
    if (!state) return;
    const id = window.setTimeout(() => setState(null), 2000);
    return () => window.clearTimeout(id);
  }, [state]);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setState("ok");
    } catch {
      setState("fail");
    }
  };
  return (
    <button type="button" className="btn-secondary" onClick={copy} aria-live="polite">
      {state === "ok" ? <Check size={16} aria-hidden /> : <Link2 size={16} aria-hidden />}
      {state === "ok" ? "Link copiado" : state === "fail" ? "Não foi possível copiar" : "Copiar link"}
    </button>
  );
}

/* --------------------------------------------------------------- the page */

function DeepDive({ ready, journey }: { ready: boolean; journey?: JourneyStatus }) {
  const nav: DeviationNav = useDeviationState();
  const { state, level } = nav;
  const forecast = LENS_OF[state.cmp] === "previsao";

  const base = useMemo<Params>(() => apiParams(state), [state]);
  const focusParams = useMemo<Params>(
    () => (state.sel && level !== "series" ? { ...base, focus_level: level, focus: state.sel } : base),
    [base, level, state.sel],
  );

  const summaryQ = useGet<SummaryPayload>(ready ? SUMMARY_PATH : null, base);
  const focusQ = useGet<FocusPayload>(ready ? FOCUS_PATH : null, focusParams);
  // Previous data stays on screen while refetching, but never data of another comparison or measure
  // (the shapes and units differ).
  const current = (d?: { cmp: string; measure?: string }) =>
    !!d && d.cmp === state.cmp && (d.measure ?? base.measure) === base.measure;
  const summary = current(summaryQ.data) ? summaryQ.data : undefined;
  const focus = current(focusQ.data) ? focusQ.data : undefined;

  const comparisons = summaryQ.data?.comparisons ?? [];
  const planAvailable =
    !comparisons.length || comparisons.some((c) => LENS_OF[c.cmp] === "plano" && c.available);

  // No plan rows at all: the default comparison becomes ac_fc (unless the URL asked for one).
  const explicitCmp = useMemo(() => {
    const sp = new URLSearchParams(nav.search);
    return sp.has("cmp") || sp.has("lente");
  }, [nav.search]);
  const mustLeavePlan = !planAvailable && !explicitCmp && LENS_OF[state.cmp] === "plano";
  useEffect(() => {
    if (mustLeavePlan)
      nav.update({ cmp: "ac_fc", periodo: undefined, sel: undefined, causa: undefined }, "replace");
  }, [mustLeavePlan, nav]);

  // Month outside the comparison's window (HTTP 400): back to the default period, with a notice.
  const [periodNoticeAt, setPeriodNoticeAt] = useState<string | null>(null);
  const err = summaryQ.error;
  const periodRejected =
    !!state.periodo && err instanceof ApiError && err.status === 400 && /per[ií]odo/i.test(err.message);
  useEffect(() => {
    if (!periodRejected) return;
    setPeriodNoticeAt(toSearchParams({ ...state, periodo: undefined }).toString());
    nav.setPeriodo(undefined);
  }, [periodRejected, state, nav]);
  const notices = [
    ...(summary?.notices ?? []),
    ...(periodNoticeAt !== null && periodNoticeAt === nav.search ? [PERIOD_RESET_NOTICE] : []),
  ];

  // Adjustment modal + the 4 s "saved" notice.
  const [overrideTarget, setOverrideTarget] = useState<OverrideTarget | null>(null);
  const [savedAt, setSavedAt] = useState(0);
  useEffect(() => {
    if (!savedAt) return;
    const id = window.setTimeout(() => setSavedAt(0), SAVED_MS);
    return () => window.clearTimeout(id);
  }, [savedAt]);

  const filters = useMemo(() => focusFilters(state, level), [state, level]);
  const run = useActionRunner({ filters, openSeries: nav.openSerie, createOverride: setOverrideTarget });
  const askAction = focus?.actions?.find((a) => a.kind === "ask_ai" && !!aiQuestion(a));

  // H1 = the answer (summary headline, or the member template while a member is focused).
  const headline =
    (state.sel && focus?.focus?.member != null && focus.headline ? focus.headline : summary?.headline) ||
    (summary || summaryQ.error ? "Deep dive dos desvios" : "");

  const unavailable = summary?.available === false;
  const emptyNode = unavailable && (summary?.node?.n_series ?? 0) === 0 && Object.keys(state.path).length > 0;
  const fallbackCmp: Cmp | undefined = (() => {
    const ok = comparisons.filter((c) => c.available).map((c) => c.cmp);
    const lensDefault = LENS_DEFAULT_CMP[LENS_OF[state.cmp]];
    if (ok.includes(lensDefault) && lensDefault !== state.cmp) return lensDefault;
    return (
      ok.find((c) => c !== state.cmp && LENS_OF[c] === LENS_OF[state.cmp]) ?? ok.find((c) => c !== state.cmp)
    );
  })();
  const fallbackLabel = comparisons.find((c) => c.cmp === fallbackCmp)?.label;

  const dim = (q: { isPlaceholderData: boolean; isFetching: boolean }) =>
    clsx("transition-opacity", q.isPlaceholderData && q.isFetching && "opacity-60");

  return (
    <div className="flex flex-col gap-5">
      <RerunBanner journey={journey} />
      {!!savedAt && (
        // Sticky under the topbar: the adjustment is often created from the exceptions table or the
        // drawer, far below the top of the page, and the confirmation must be seen there too.
        <div
          role="status"
          className="sticky top-[84px] z-20 flex items-center gap-2.5 rounded-2xl bg-emerald-50 px-4 py-2.5 text-[13px] font-semibold text-emerald-800 shadow-[0_10px_24px_-14px_rgba(12,163,12,0.45)]"
        >
          <CircleCheck size={16} aria-hidden className="shrink-0" />
          {SAVED_NOTICE}
        </div>
      )}

      <div className="-mb-6">
        <PageHeader
          eyebrow="Etapa 3 de 3 · Deep dive dos desvios"
          icon={<ScanSearch />}
          title={
            headline ? (
              <span className="block max-w-[72ch] break-words text-[22px] leading-snug xl:text-[24px]">
                {headline}
              </span>
            ) : (
              <>
                <span className="sr-only">Deep dive dos desvios</span>
                <span
                  aria-hidden
                  className="block h-8 w-[min(640px,80%)] animate-pulse rounded-xl bg-[#eef1fa]"
                />
              </>
            )
          }
          actions={
            <>
              {state.de && (
                <Link to={ROUTES.relatorio(state.de, loadReportScope())} className="btn-ghost">
                  <ArrowLeft size={16} aria-hidden /> Voltar ao relatório · {CHAPTER_SHORT[state.de]}
                </Link>
              )}
              <CopyLinkButton />
              <button
                type="button"
                className="btn-primary"
                disabled={!askAction}
                title={askAction ? aiQuestion(askAction) : "Sem pergunta sugerida para este recorte"}
                onClick={() => askAction && run(askAction)}
              >
                <Sparkles size={16} aria-hidden /> Perguntar à IA
              </button>
            </>
          }
        />
      </div>

      <ControlBar nav={nav} summary={summaryQ.data} planAvailable={planAvailable} />
      <Breadcrumb nav={nav} summary={summaryQ.data} />
      <NoticeChips notices={notices} />

      {emptyNode ? (
        <section className="card">
          <EmptyState title="Nenhuma série neste recorte" icon={<ScanSearch />}>
            <div className="flex flex-col items-center gap-4">
              <p>O caminho escolhido não corresponde a nenhuma série da base ativa.</p>
              <button type="button" className="btn-primary" onClick={nav.resetPath}>
                Voltar para Empresa toda
              </button>
            </div>
          </EmptyState>
        </section>
      ) : unavailable ? (
        <section className="card">
          <EmptyState title="Comparação indisponível" icon={<ScanSearch />}>
            <div className="flex flex-col items-center gap-4">
              <p>{summary?.reason ?? "Não há dados para esta comparação."}</p>
              {/* A month or quarter without plan rows: the comparison's own window first. */}
              {(state.periodo || fallbackCmp) && (
                <div className="flex flex-wrap justify-center gap-2">
                  {state.periodo && (
                    <button type="button" className="btn-primary" onClick={() => nav.setPeriodo(undefined)}>
                      <RotateCcw size={16} aria-hidden /> Voltar ao período padrão
                    </button>
                  )}
                  {fallbackCmp && (
                    <button
                      type="button"
                      className={state.periodo ? "btn-secondary" : "btn-primary"}
                      onClick={() => nav.setCmp(fallbackCmp)}
                    >
                      <RotateCcw size={16} aria-hidden /> Ver {fallbackLabel ?? "a comparação padrão"}
                    </button>
                  )}
                </div>
              )}
            </div>
          </EmptyState>
        </section>
      ) : (
        <>
          <div className={dim(summaryQ)}>
            <KpiStrip
              kpis={summary?.kpis}
              loading={!summary}
              error={summary ? null : periodRejected ? null : err}
            />
          </div>
          <div className="grid gap-6 xl:grid-cols-12">
            <WherePanel
              nav={nav}
              summary={summary}
              stale={summaryQ.isPlaceholderData}
              error={periodRejected ? null : err}
              className={clsx("xl:col-span-7", dim(summaryQ))}
            />
            <WhyPanel
              nav={nav}
              focus={focus}
              error={focusQ.error}
              onRun={run}
              className={clsx("xl:col-span-5", dim(focusQ))}
            />
          </div>
          <WhenPanel nav={nav} focus={focus} error={focusQ.error} className={dim(focusQ)} />
          <ExceptionsTable
            enabled={ready}
            params={forecast && state.causa ? { ...focusParams, cause: state.causa } : focusParams}
            forecast={forecast}
            withProb={state.cmp === "fc_pl" || state.cmp === "fc_tg"}
            measure={forecast ? "revenue" : state.medida}
            causa={forecast ? state.causa : undefined}
            causaLabel={focus?.causes?.find((c) => c.code === state.causa)?.label}
            onClearCausa={() => nav.toggleCausa(undefined)}
            onOpenSeries={nav.openSerie}
            onRun={(a) => run(a)}
          />
        </>
      )}

      <SeriesDrawer nav={nav} onRun={run} enabled={ready} />
      {overrideTarget && (
        <OverrideModal
          target={overrideTarget}
          onClose={() => setOverrideTarget(null)}
          onSaved={() => {
            setOverrideTarget(null);
            setSavedAt(Date.now());
          }}
        />
      )}
    </div>
  );
}

/** Stage 3 · Desvios. Locked (JourneyGate) until an active completed run exists (spec §1.5). */
export default function Desvios() {
  const journeyQ = useJourney();
  const journey = journeyQ.data;
  if (journey && journey.stage !== "pronto") return <JourneyGate journey={journey} />;
  return <DeepDive ready={journey?.stage === "pronto" || journeyQ.isError} journey={journey} />;
}
