/**
 * Horizontal stepper of the Entrada stage (spec §2.1, item 2): "Base de dados" · "Competição de
 * modelos" · "Confiança no forecast". A done node is a button that opens its section; the node of the
 * current stage carries `aria-current="step"`. State is never shown by colour alone: icon + words.
 */
import clsx from "clsx";
import { CircleAlert, CircleCheck } from "lucide-react";

export type StepId = 1 | 2 | 3;
export type StepState = "done" | "active" | "waiting" | "error";

export interface StepperItem {
  id: StepId;
  label: string;
  state: StepState;
  /** Short status under the label ("Base validada", "Em andamento · 63%"). */
  hint: string;
}

const NODE: Record<StepState, string> = {
  done: "bg-emerald-50 text-emerald-600 ring-1 ring-emerald-200",
  active:
    "bg-gradient-to-br from-[#5b9cff] to-[#3483fa] text-white shadow-[0_8px_18px_-8px_rgba(52,131,250,0.9)]",
  waiting: "bg-[#eef1fa] text-muted",
  error: "bg-red-50 text-red-600 ring-1 ring-red-200",
};

const HINT: Record<StepState, string> = {
  done: "text-emerald-700",
  active: "text-brand-dark",
  waiting: "text-muted",
  error: "text-red-700",
};

/** Words read by screen readers next to each node (the visual hint may be more specific). */
const STATE_WORD: Record<StepState, string> = {
  done: "concluída",
  active: "em andamento",
  waiting: "aguardando",
  error: "requer atenção",
};

function NodeIcon({ step }: { step: StepperItem }) {
  return (
    <span
      aria-hidden
      className={clsx(
        "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold tabular",
        NODE[step.state],
      )}
    >
      {step.state === "done" ? (
        <CircleCheck size={18} strokeWidth={2.4} />
      ) : step.state === "error" ? (
        <CircleAlert size={18} strokeWidth={2.4} />
      ) : (
        step.id
      )}
    </span>
  );
}

function NodeText({ step }: { step: StepperItem }) {
  return (
    <span className="min-w-0 text-left">
      <span className="block break-words text-[13.5px] font-semibold leading-snug text-ink">
        {step.label}
      </span>
      <span className={clsx("mt-0.5 block break-words text-[12px] leading-snug", HINT[step.state])}>
        {step.hint}
      </span>
      <span className="sr-only"> ({STATE_WORD[step.state]})</span>
    </span>
  );
}

export function Stepper({
  steps,
  current,
  onOpen,
}: {
  steps: StepperItem[];
  /** Step of the current stage (gets `aria-current="step"`). */
  current?: StepId;
  /** Opens (expands and scrolls to) the section of a done step. */
  onOpen: (id: StepId) => void;
}) {
  return (
    <ol
      aria-label="Etapas da entrada"
      className="card flex flex-col gap-4 px-6 py-5 md:flex-row md:items-center md:gap-3"
    >
      {steps.map((step, i) => (
        <li
          key={step.id}
          aria-current={current === step.id ? "step" : undefined}
          className="flex min-w-0 flex-1 items-center gap-3"
        >
          {step.state === "done" ? (
            <button
              type="button"
              onClick={() => onOpen(step.id)}
              className="-m-1.5 flex min-w-0 items-center gap-3 rounded-2xl p-1.5 transition hover:bg-[#f4f7ff] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              <NodeIcon step={step} />
              <NodeText step={step} />
            </button>
          ) : (
            <div className="flex min-w-0 items-center gap-3">
              <NodeIcon step={step} />
              <NodeText step={step} />
            </div>
          )}
          {i < steps.length - 1 && (
            <span
              aria-hidden
              className={clsx(
                "ml-1 hidden h-px min-w-6 flex-1 md:block",
                step.state === "done" ? "bg-emerald-200" : "bg-line",
              )}
            />
          )}
        </li>
      ))}
    </ol>
  );
}

export default Stepper;
