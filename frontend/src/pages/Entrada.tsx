/**
 * Stage 1 · Entrada (spec §2.1): "A base está pronta, os modelos competiram e posso confiar no número?"
 *
 * One calm column (max 1120 px): header, stepper, rerun banner and three step cards — base de dados,
 * competição de modelos, confiança no forecast. The journey state (`GET /api/journey`) decides which
 * step is expanded; `?acao=carregar` opens step 1. When everything is ready the page reads as a
 * one-screen verdict whose main button is "Abrir o relatório".
 */
import { ArrowRight, FlaskConical } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { StepData } from "../components/entrada/StepData";
import { StepModels } from "../components/entrada/StepModels";
import { Stepper, type StepId, type StepperItem } from "../components/entrada/Stepper";
import { StepTrust } from "../components/entrada/StepTrust";
import { Skeleton } from "../components/entrada/shared";
import { stepAnchorId, VERDICT_SHORT } from "../components/entrada/helpers";
import { RerunBanner } from "../components/journey/RerunBanner";
import { RunForecastButton } from "../components/RunControls";
import { ErrorState, PageHeader } from "../components/ui";
import { useGet } from "../hooks/useApi";
import { runProgressPct, useJourney } from "../hooks/useJourney";
import { full } from "../lib/format";
import { ROUTES } from "../lib/routes";
import type { DatasetInfo } from "../types";
import type { JourneyStage, JourneyStatus } from "../types/journey";
import { isTrustAvailable, type TrustResponse } from "../types/trust";

/** Step expanded by default in each stage (spec §2.1 "Expansion rules"). */
const STAGE_STEP: Record<JourneyStage, StepId> = { dados: 1, modelos: 2, pronto: 3 };

/** Gives `RunForecastButton` (always a primary button) the secondary look next to "Abrir o relatório". */
const AS_SECONDARY =
  "[&>button]:border [&>button]:border-line [&>button]:bg-white/90 [&>button]:bg-none [&>button]:text-ink [&>button]:shadow-[0_2px_8px_-4px_rgba(45,50,119,0.18)] [&>button]:hover:bg-white";

/** A run completion scrolls step 3 into view only if the user has not scrolled for this long. */
const SCROLL_IDLE_MS = 3000;

function stepperItems(
  j: JourneyStatus,
  dataError: boolean,
  trust: TrustResponse | undefined,
  trustError: boolean,
): StepperItem[] {
  const ready = j.stage === "pronto";
  const running = j.run.state === "running";
  const pctText = `${runProgressPct(j.run.progress)}%`;
  const available = isTrustAvailable(trust) ? trust : null;

  const s1: StepperItem = dataError
    ? { id: 1, label: "Base de dados", state: "error", hint: "Base recusada na validação" }
    : j.dataset
      ? { id: 1, label: "Base de dados", state: "done", hint: "Base validada" }
      : { id: 1, label: "Base de dados", state: "active", hint: "Carregue uma base" };

  let s2: StepperItem;
  if (ready)
    s2 = {
      id: 2,
      label: "Competição de modelos",
      state: "done",
      hint: running
        ? `Nova execução · ${pctText}`
        : available
          ? `${full(available.run.n_models)} modelos · ${full(available.run.n_series)} séries`
          : "Concluída",
    };
  else if (!j.dataset)
    s2 = { id: 2, label: "Competição de modelos", state: "waiting", hint: "Aguardando a base" };
  else if (running)
    s2 = { id: 2, label: "Competição de modelos", state: "active", hint: `Em andamento · ${pctText}` };
  else if (j.run.state === "failed")
    s2 = { id: 2, label: "Competição de modelos", state: "error", hint: "A execução falhou" };
  else s2 = { id: 2, label: "Competição de modelos", state: "active", hint: "Pronta para rodar" };

  let s3: StepperItem;
  if (!ready)
    s3 = { id: 3, label: "Confiança no forecast", state: "waiting", hint: "Aguardando a competição" };
  else if (available)
    s3 = {
      id: 3,
      label: "Confiança no forecast",
      state: available.verdict.code === "nao_confiavel" ? "error" : "done",
      hint: VERDICT_SHORT[available.verdict.code] ?? available.verdict.label,
    };
  else if (trustError)
    s3 = { id: 3, label: "Confiança no forecast", state: "error", hint: "Veredito indisponível" };
  else s3 = { id: 3, label: "Confiança no forecast", state: "active", hint: "Calculando o veredito" };

  return [s1, s2, s3];
}

type Toggles = Partial<Record<StepId, boolean>>;

export default function Entrada() {
  const [params] = useSearchParams();
  const wantsUpload = params.get("acao") === "carregar";

  const journeyQ = useJourney();
  const journey = journeyQ.data;
  const stage = journey?.stage;
  const ready = stage === "pronto";
  const activeQ = useGet<DatasetInfo>(journey?.dataset ? "/api/data/active" : null, undefined, {
    retry: false,
  });
  const trustQ = useGet<TrustResponse>(ready ? "/api/models/trust" : null);
  const trust = ready ? trustQ.data : undefined;
  const trustError = ready ? trustQ.error : null;

  const [dataError, setDataError] = useState(false);

  /* Expansion: the stage decides the default; the user's toggles last until the stage changes. */
  const [view, setView] = useState<{ stage?: JourneyStage; acao: boolean; toggles: Toggles }>(() => ({
    acao: wantsUpload,
    toggles: wantsUpload ? { 1: true } : {},
  }));
  const stageChanged = !!stage && view.stage !== stage;
  if (stageChanged || wantsUpload !== view.acao) {
    // The first stage seen keeps the ?acao=carregar toggle; a later stage change resets to its default.
    let toggles = stageChanged && view.stage !== undefined ? {} : view.toggles;
    if (wantsUpload && !view.acao) toggles = { ...toggles, 1: true };
    setView({ stage: stage ?? view.stage, acao: wantsUpload, toggles });
  }
  const defaultStep = stage ? STAGE_STEP[stage] : 1;
  // Once pronto, step 2 has nothing left to operate: its "collapsed" form is the competition result
  // itself (headline + placar + insight + facts, spec §2.1 step 2 "completed", F3 acceptance "a pronto
  // fixture shows … ≤ 7 scoreboard rows"), so the models stay on the entrance; "Recolher" hides it.
  const isOpen = (id: StepId) => view.toggles[id] ?? (defaultStep === id || (stage === "pronto" && id === 2));
  const setOpen = (id: StepId, open: boolean) =>
    setView((v) => ({ ...v, toggles: { ...v.toggles, [id]: open } }));
  const scrollTo = (id: StepId) =>
    requestAnimationFrame(() =>
      document.getElementById(stepAnchorId(id))?.scrollIntoView?.({ behavior: "smooth", block: "start" }),
    );

  /* A run that completes during the visit brings the verdict into view (unless the user is scrolling). */
  const lastUserScroll = useRef(0);
  useEffect(() => {
    const mark = () => {
      lastUserScroll.current = Date.now();
    };
    document.addEventListener("scroll", mark, { capture: true, passive: true });
    return () => document.removeEventListener("scroll", mark, { capture: true });
  }, []);
  const runState = journey?.run.state;
  const prevRunState = useRef(runState);
  useEffect(() => {
    if (
      prevRunState.current === "running" &&
      runState === "completed" &&
      Date.now() - lastUserScroll.current > SCROLL_IDLE_MS
    ) {
      document.getElementById(stepAnchorId(3))?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    }
    prevRunState.current = runState;
  }, [runState]);

  const header = (
    <PageHeader
      eyebrow="Etapa 1 de 3"
      icon={<FlaskConical />}
      title="Dados e modelos"
      subtitle="Antes da história, a confiança: valide a base, deixe os modelos competirem e veja quanto o forecast merece crédito."
      actions={
        ready ? (
          <>
            <span className={AS_SECONDARY}>
              <RunForecastButton label="Rodar novamente" />
            </span>
            <Link className="btn-primary" to={ROUTES.relatorio("resumo")}>
              Abrir o relatório <ArrowRight size={16} aria-hidden />
            </Link>
          </>
        ) : undefined
      }
    />
  );

  if (!journey) {
    return (
      <div className="mx-auto w-full max-w-[1120px]">
        {header}
        {journeyQ.error ? (
          <ErrorState error={journeyQ.error} />
        ) : (
          <div className="space-y-6" aria-busy>
            <Skeleton className="h-[78px] rounded-3xl" />
            <Skeleton className="h-[150px] rounded-3xl" />
            <Skeleton className="h-[150px] rounded-3xl" />
            <Skeleton className="h-[150px] rounded-3xl" />
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-[1120px]">
      {header}
      <div className="space-y-6">
        <Stepper
          steps={stepperItems(journey, dataError, trust, !!trustError)}
          current={STAGE_STEP[journey.stage]}
          onOpen={(id) => {
            setOpen(id, true);
            scrollTo(id);
          }}
        />
        <RerunBanner journey={journey} />
        <StepData
          journey={journey}
          active={activeQ.data}
          expanded={!journey.dataset || isOpen(1)}
          onExpand={() => setOpen(1, true)}
          onCollapse={() => setOpen(1, false)}
          onDataError={setDataError}
        />
        <StepModels
          journey={journey}
          trust={trust}
          trustLoading={trustQ.isLoading}
          trustError={trustError}
          expanded={isOpen(2)}
          onToggle={() => setOpen(2, !isOpen(2))}
        />
        <StepTrust
          journey={journey}
          trust={trust}
          trustLoading={trustQ.isLoading}
          trustError={trustError}
          expanded={isOpen(3)}
          onToggle={() => setOpen(3, !isOpen(3))}
        />
      </div>
    </div>
  );
}
