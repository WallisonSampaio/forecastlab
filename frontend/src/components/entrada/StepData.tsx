/**
 * Step 1 of the Entrada stage, "Base de dados" (spec §2.1, item 4): the collapsed summary of the active
 * base, the two option cards (demo / own spreadsheet), the upload and demo mutations and their result
 * cards. A blocked upload is never stored (the previous base stays active), so its state comes from the
 * upload response, not from `/api/journey`. An upload accepted while a run is in progress would be
 * activated without a run, so the UI blocks both options while `run.state === "running"`.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  CircleCheck,
  FileSpreadsheet,
  Loader2,
  Sparkles,
  TriangleAlert,
  Upload,
  UploadCloud,
} from "lucide-react";
import { useId, useRef, useState, type DragEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { full, monthLabel } from "../../lib/format";
import { ROUTES } from "../../lib/routes";
import { api } from "../../services/api";
import type { DatasetInfo, Issue, ValidationReport } from "../../types";
import type { JourneyDataset, JourneyStatus } from "../../types/journey";
import { IssueItem, planLabel, ptError } from "../data/health";
import { RunForecastButton } from "../RunControls";
import { Card, ErrorState, IconTile } from "../ui";
import { plural, stepAnchorId } from "./helpers";
import { Notice } from "./shared";

/** `POST /api/data/upload` response (api/data.py). */
export interface UploadResult {
  file_name: string;
  accepted: boolean;
  dataset_version: string | null;
  run_id: string | null;
  /** pt-BR reason when the base was stored but its run could not start. */
  run_message?: string;
  validation: ValidationReport;
  quality_label?: string;
}

/** `POST /api/data/demo` response. */
export interface DemoResult {
  dataset_version: string;
  run_id: string | null;
}

export const TEMPLATE_PATH = "/api/data/template";
export const ACCEPTED_FILES = ".xlsx,.xls,.csv,.parquet";
const DEMO_BODY = { seed: 42, run_forecast: true };

/** Result of the last upload / demo load. `version` is the base it activated (none when blocked). */
type Outcome =
  | { kind: "blocked"; file: string; issues: Issue[]; hadBase: boolean }
  | { kind: "not_started"; version: string | null; message: string; warnings: Issue[] }
  | { kind: "warnings"; version: string | null; warnings: Issue[] }
  | { kind: "valid"; version: string | null };

const issuesOf = (v: ValidationReport | undefined, sev: Issue["severity"]) =>
  (v?.issues ?? []).filter((i) => i.severity === sev);

function outcomeOfUpload(r: UploadResult, hadBase: boolean): Outcome {
  if (!r.accepted) {
    const critical = issuesOf(r.validation, "critical");
    return {
      kind: "blocked",
      file: r.file_name,
      issues: critical.length ? critical : (r.validation?.issues ?? []),
      hadBase,
    };
  }
  const warnings = issuesOf(r.validation, "warning");
  const version = r.dataset_version;
  if (!r.run_id)
    return {
      kind: "not_started",
      version,
      message: r.run_message?.trim() || "a execução não foi iniciada.",
      warnings,
    };
  return warnings.length ? { kind: "warnings", version, warnings } : { kind: "valid", version };
}

/**
 * An acceptance card is news only until the journey moves on: "já começou" disappears once the run of
 * that base completed, and "não começou" once a run of that base is running or completed.
 */
function outcomeVisible(o: Outcome, journey: JourneyStatus): boolean {
  if (o.kind === "blocked") return true;
  if (!o.version || journey.dataset?.version !== o.version) return true;
  const state = journey.run.state;
  if (o.kind === "not_started") return state !== "running" && state !== "completed";
  return !(state === "completed" && journey.stage === "pronto");
}

/* ------------------------------------------------------------------ plan chip */

const isDemoPlan = (src: string | null) => !!src && /sint[eé]tic|synthetic/i.test(src);

/** Origin of the budget and target (spec §2.1, plan chip): uploaded, demo, or derived (amber). */
export function PlanChip({ dataset }: { dataset: JourneyDataset }) {
  const base =
    "inline-flex max-w-full items-start gap-1.5 rounded-xl px-3 py-1.5 text-[12px] leading-snug ring-1";
  if (dataset.plan_derived)
    return (
      <span
        data-testid="plano-chip"
        title={planLabel(dataset.plan_source)}
        className={clsx(base, "bg-amber-50 text-amber-900 ring-amber-200/80")}
      >
        <TriangleAlert size={14} aria-hidden className="mt-px shrink-0 text-amber-600" />
        <span className="min-w-0 break-words">
          Orçamento e meta <strong>estimados automaticamente</strong> (ano anterior + 5%) — desvios vs
          orçamento são ilustrativos
        </span>
      </span>
    );
  const text = !dataset.has_plan
    ? "Orçamento e meta: não informados"
    : isDemoPlan(dataset.plan_source)
      ? "Orçamento e meta: base de demonstração"
      : "Orçamento e meta: enviados na planilha";
  return (
    <span
      data-testid="plano-chip"
      title={dataset.has_plan ? planLabel(dataset.plan_source) : undefined}
      className={clsx(base, "bg-[#f4f6fc] text-ink-2 ring-[#e7eaf5]")}
    >
      <span className="min-w-0 break-words">{text}</span>
    </span>
  );
}

/* ------------------------------------------------------------- summary line */

function Summary({
  dataset,
  active,
  changing,
  onChange,
}: {
  dataset: JourneyDataset;
  active?: DatasetInfo | null;
  /** The option cards are open: the "Trocar base" link is redundant. */
  changing: boolean;
  onChange: () => void;
}) {
  const score = dataset.quality_score ?? active?.validation?.quality.overall ?? null;
  const label = dataset.quality_label ?? active?.quality_label ?? null;
  const treated = [...issuesOf(active?.validation, "critical"), ...issuesOf(active?.validation, "warning")];
  return (
    <div>
      <div className="flex items-start gap-3">
        <CircleCheck size={20} aria-hidden className="mt-0.5 shrink-0 text-emerald-600" />
        <p className="min-w-0 break-words text-[15px] leading-relaxed text-ink-2" data-testid="base-resumo">
          Base validada: <strong className="text-ink">{full(dataset.n_series)} séries</strong> Cliente × SKU ·{" "}
          <strong className="text-ink">{full(dataset.n_months)} meses</strong> (
          {monthLabel(dataset.start_date)}–{monthLabel(dataset.end_date)}) · qualidade{" "}
          <strong className="text-ink">{score == null ? "—" : `${Math.round(score)}/100`}</strong>
          {label ? ` (${label})` : ""}
        </p>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 pl-8">
        <PlanChip dataset={dataset} />
        <Link
          to={ROUTES.bases("diagnostico")}
          className="text-[13px] font-semibold text-brand hover:text-brand-dark hover:underline"
        >
          Ver diagnóstico completo
        </Link>
        {!changing && (
          <button
            type="button"
            onClick={onChange}
            className="text-[13px] font-semibold text-brand hover:text-brand-dark hover:underline"
          >
            Trocar base
          </button>
        )}
      </div>
      {treated.length > 0 && (
        <details className="group mt-3 pl-8">
          <summary className="cursor-pointer text-[12.5px] font-medium text-muted hover:text-ink-2">
            {treated.length}{" "}
            {plural(treated.length, "aviso tratado automaticamente", "avisos tratados automaticamente")} na
            validação
          </summary>
          <ul className="mt-3 space-y-2.5">
            {treated.map((i, k) => (
              <IssueItem key={`${i.code}-${k}`} issue={i} />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- result cards */

function OutcomeCard({ outcome, templateHref }: { outcome: Outcome; templateHref: string }) {
  switch (outcome.kind) {
    case "blocked":
      return (
        <Notice
          tone="bad"
          role="alert"
          data-testid="upload-bloqueado"
          title={
            outcome.hadBase
              ? "A base tem erros críticos e não foi carregada. A base anterior continua ativa."
              : "A base tem erros críticos e não foi carregada."
          }
        >
          <p className="break-words text-red-800/90">Arquivo: {outcome.file}</p>
          <ul className="mt-3 space-y-2.5 text-ink">
            {outcome.issues.map((i, k) => (
              <IssueItem key={`${i.code}-${k}`} issue={i} />
            ))}
          </ul>
          <a className="btn-secondary mt-3" href={templateHref}>
            <FileSpreadsheet size={15} aria-hidden className="text-emerald-600" /> Baixar modelo de planilha
          </a>
        </Notice>
      );
    case "not_started":
      return (
        <Notice
          tone="warn"
          role="status"
          data-testid="upload-sem-execucao"
          title={`Base carregada e ativada, mas a competição de modelos não começou: ${outcome.message}`}
        >
          <div className="mt-1">
            <RunForecastButton />
          </div>
          {outcome.warnings.length > 0 && <WarningList warnings={outcome.warnings} />}
        </Notice>
      );
    case "warnings":
      return (
        <Notice
          tone="warn"
          role="status"
          data-testid="upload-avisos"
          title={`Base aceita com ${outcome.warnings.length} ${plural(
            outcome.warnings.length,
            "aviso tratado automaticamente",
            "avisos tratados automaticamente",
          )} — a competição de modelos já começou.`}
        >
          <WarningList warnings={outcome.warnings} />
        </Notice>
      );
    case "valid":
      return (
        <Notice
          tone="good"
          role="status"
          data-testid="upload-valido"
          title="Base válida — a competição de modelos já começou."
        />
      );
  }
}

function WarningList({ warnings }: { warnings: Issue[] }) {
  return (
    <details className="mt-2">
      <summary className="cursor-pointer font-medium">
        Ver {plural(warnings.length, "o aviso", `os ${warnings.length} avisos`)}
      </summary>
      <ul className="mt-3 space-y-2.5 text-ink">
        {warnings.map((i, k) => (
          <IssueItem key={`${i.code}-${k}`} issue={i} />
        ))}
      </ul>
    </details>
  );
}

/* ------------------------------------------------------------- option cards */

function OptionCard({
  icon,
  tone,
  title,
  children,
}: {
  icon: ReactNode;
  tone: "blue" | "teal";
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-4 rounded-3xl bg-white/70 p-5 ring-1 ring-[#e9ecf6]">
      <div className="flex items-center gap-3">
        <IconTile icon={icon} tone={tone} size="md" />
        <h4 className="text-[15px] font-semibold leading-snug text-ink">{title}</h4>
      </div>
      {children}
    </div>
  );
}

/* --------------------------------------------------------------------- card */

export function StepData({
  journey,
  active,
  expanded,
  onExpand,
  onCollapse,
  onDataError,
}: {
  journey: JourneyStatus;
  /** `GET /api/data/active` (validation issues and quality of the active base). */
  active?: DatasetInfo | null;
  /** Options visible (always true without a dataset). */
  expanded: boolean;
  onExpand: () => void;
  onCollapse: () => void;
  /** Tells the stepper whether the last attempt was refused (blocked or rejected upload). */
  onDataError?: (failed: boolean) => void;
}) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const hintId = useId();
  const bodyId = `${stepAnchorId(1)}-corpo`;
  const [drag, setDrag] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const dataset = journey.dataset;
  const hadBase = !!dataset;
  const runBusy = journey.run.state === "running";

  const upload = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return api.post<UploadResult>("/api/data/upload", fd);
    },
    onSuccess: (r) => {
      setOutcome(outcomeOfUpload(r, hadBase));
      onDataError?.(!r.accepted);
      if (r.accepted) {
        onCollapse();
        qc.invalidateQueries();
      }
    },
    onError: () => onDataError?.(true),
  });
  const demo = useMutation({
    mutationFn: () => api.post<DemoResult>("/api/data/demo", DEMO_BODY),
    onSuccess: (r) => {
      setOutcome(
        r.run_id
          ? { kind: "valid", version: r.dataset_version }
          : {
              kind: "not_started",
              version: r.dataset_version,
              message: "a execução não foi iniciada.",
              warnings: [],
            },
      );
      onDataError?.(false);
      onCollapse();
      qc.invalidateQueries();
    },
  });
  const working = upload.isPending || demo.isPending;
  const disabled = runBusy || working;
  const templateHref = api.url(TEMPLATE_PATH);

  const reset = () => {
    setOutcome(null);
    upload.reset();
    demo.reset();
    onDataError?.(false);
  };
  /** "Manter a base atual": the refused attempt (blocked or rejected file) is dismissed with the cards. */
  const keepCurrent = () => {
    if (outcome?.kind === "blocked" || upload.error || demo.error) reset();
    onCollapse();
  };
  const pick = (file?: File | null) => {
    if (!file || disabled) return;
    reset();
    setFileName(file.name);
    upload.mutate(file);
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    pick(e.dataTransfer.files?.[0]);
  };

  const showOptions = expanded || !dataset;

  return (
    <Card
      id={stepAnchorId(1)}
      className="scroll-mt-24"
      data-visual="base"
      data-question="A base está pronta para prever?"
      title="Base de dados"
      subtitle="A base está pronta para prever?"
      actions={
        dataset && expanded ? <ToggleCollapse controls={bodyId} onCollapse={keepCurrent} /> : undefined
      }
    >
      <div id={bodyId} className="space-y-5">
        <div aria-live="polite" className="space-y-3 empty:hidden">
          {upload.error && <ErrorState error={ptError(upload.error)} />}
          {demo.error && <ErrorState error={ptError(demo.error)} />}
          {outcome && outcomeVisible(outcome, journey) && (
            <OutcomeCard outcome={outcome} templateHref={templateHref} />
          )}
        </div>

        {dataset && <Summary dataset={dataset} active={active} changing={showOptions} onChange={onExpand} />}

        {showOptions && (
          <div className="space-y-4">
            {runBusy && (
              <p
                id={hintId}
                className="flex items-center gap-2 rounded-2xl bg-[#eef5ff] px-4 py-2.5 text-[13px] font-medium text-[#1f4f9e]"
              >
                <Loader2 size={15} aria-hidden className="shrink-0 animate-spin" />
                Aguarde a execução atual terminar.
              </p>
            )}
            <div className="grid gap-4 md:grid-cols-2">
              <OptionCard icon={<Sparkles />} tone="blue" title="Usar base de demonstração">
                <p className="text-[13.5px] leading-relaxed text-ink-2">
                  Base sintética com ~220 séries Cliente × SKU, 5 anos de histórico, orçamento, meta e
                  histórico de ajustes comerciais.
                </p>
                <div className="space-y-2">
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={disabled}
                    aria-describedby={runBusy ? hintId : undefined}
                    onClick={() => {
                      reset();
                      demo.mutate();
                    }}
                  >
                    {demo.isPending ? (
                      <Loader2 size={16} aria-hidden className="animate-spin" />
                    ) : (
                      <Sparkles size={16} aria-hidden />
                    )}
                    {demo.isPending ? "Carregando demonstração…" : "Carregar demonstração e rodar forecast"}
                  </button>
                  <p className="text-[12px] leading-relaxed text-muted">
                    A competição de modelos leva cerca de 5 minutos; o progresso aparece no passo 2.
                  </p>
                </div>
              </OptionCard>

              <OptionCard icon={<Upload />} tone="teal" title="Enviar minha planilha">
                <button
                  type="button"
                  data-testid="dropzone"
                  disabled={disabled}
                  aria-describedby={runBusy ? hintId : undefined}
                  onClick={() => input.current?.click()}
                  onDragOver={(e) => {
                    e.preventDefault();
                    if (!disabled) setDrag(true);
                  }}
                  onDragLeave={() => setDrag(false)}
                  onDrop={onDrop}
                  className={clsx(
                    "flex w-full flex-col items-center justify-center gap-1.5 rounded-2xl border-2 border-dashed px-4 py-6 text-center transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                    disabled
                      ? "cursor-not-allowed border-[#e1e5f1] bg-[#f7f8fd] opacity-70"
                      : drag
                        ? "border-brand bg-[#eef5ff]"
                        : "border-[#d5daeb] bg-white/60 hover:border-brand/60 hover:bg-[#f4f7ff]",
                  )}
                >
                  {upload.isPending ? (
                    <>
                      <Loader2 size={24} aria-hidden className="animate-spin text-brand" />
                      <span className="break-words text-sm font-semibold text-ink">
                        Validando {fileName ?? "arquivo"}…
                      </span>
                    </>
                  ) : (
                    <>
                      <UploadCloud size={26} aria-hidden className="text-[#0b8790]" />
                      <span className="text-sm font-semibold text-ink">
                        Arraste o arquivo ou clique para escolher
                      </span>
                      <span className="text-xs text-muted">.xlsx · .csv · .parquet · até 50 MB</span>
                    </>
                  )}
                </button>
                <input
                  ref={input}
                  type="file"
                  accept={ACCEPTED_FILES}
                  className="sr-only"
                  tabIndex={-1}
                  aria-label="Arquivo da base de vendas"
                  data-testid="arquivo-base"
                  disabled={disabled}
                  onChange={(e) => {
                    pick(e.target.files?.[0]);
                    e.target.value = "";
                  }}
                />
                <a className="btn-secondary self-start" href={templateHref}>
                  <FileSpreadsheet size={15} aria-hidden className="text-emerald-600" /> Baixar modelo de
                  planilha (.xlsx)
                </a>
                <p className="text-[12px] leading-relaxed text-muted">
                  Colunas mínimas: Data, Região, Canal, Cliente, SKU e Unidades. Orçamento e meta entram pela
                  aba 'Plano (opcional)'.
                </p>
              </OptionCard>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

function ToggleCollapse({ controls, onCollapse }: { controls: string; onCollapse: () => void }) {
  return (
    <button
      type="button"
      aria-expanded
      aria-controls={controls}
      onClick={onCollapse}
      className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-[12.5px] font-semibold text-ink-2 transition hover:bg-[#eef1fa] hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
    >
      Manter a base atual
    </button>
  );
}

export default StepData;
