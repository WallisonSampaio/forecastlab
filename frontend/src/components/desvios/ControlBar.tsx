/**
 * Deep-dive controls (spec §2.3.3): Lente [Plano | Previsão] · Comparação · Período · Medida.
 * Unavailable choices stay visible but disabled, with the reason in words (never hidden).
 */
import clsx from "clsx";
import { useId, type ReactNode } from "react";

import { CMPS, DEFAULT_PERIOD, LENS_OF, type Cmp, type Lente, type Medida } from "../../lib/deviationsUrl";
import { Segmented } from "../ui";
import { CMP_FALLBACK_LABEL, type DeviationNav, type SummaryPayload } from "./state";

/** Reason suffix of a disabled comparison (spec §2.3.3). */
const disabledSuffix = (cmp: Cmp, reason?: string) =>
  LENS_OF[cmp] === "plano"
    ? "sem orçamento nesta base"
    : cmp === "ac_cs"
      ? "sem histórico de ajustes"
      : (reason ?? "indisponível nesta base").replace(/\.$/, "").replace(/^./, (c) => c.toLowerCase());

export const PLAN_LOCKED_HINT = "Sem orçamento/meta nesta base";

function Control({ label, htmlFor, children }: { label: string; htmlFor?: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      {htmlFor ? (
        <label htmlFor={htmlFor} className="label-xs">
          {label}
        </label>
      ) : (
        <span className="label-xs">{label}</span>
      )}
      {children}
    </div>
  );
}

/** Lens toggle: like `Segmented`, plus a disabled option with its reason. */
function LensToggle({
  value,
  planAvailable,
  onChange,
}: {
  value: Lente;
  planAvailable: boolean;
  onChange: (l: Lente) => void;
}) {
  const hintId = useId();
  const options: { value: Lente; label: string; disabled: boolean }[] = [
    { value: "plano", label: "Plano", disabled: !planAvailable },
    { value: "previsao", label: "Previsão", disabled: false },
  ];
  return (
    <div role="group" aria-label="Lente" className="inline-flex w-fit rounded-xl bg-[#eef1fa] p-1">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          disabled={o.disabled}
          title={o.disabled ? PLAN_LOCKED_HINT : undefined}
          aria-describedby={o.disabled ? hintId : undefined}
          onClick={() => onChange(o.value)}
          className={clsx(
            "whitespace-nowrap rounded-lg px-3.5 py-1.5 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            value === o.value
              ? "bg-white text-ink shadow-[0_4px_10px_-4px_rgba(45,50,119,0.3)]"
              : "text-muted hover:text-ink",
            o.disabled && "cursor-not-allowed opacity-50 hover:text-muted",
          )}
        >
          {o.label}
        </button>
      ))}
      {!planAvailable && (
        <span id={hintId} className="sr-only">
          {PLAN_LOCKED_HINT}
        </span>
      )}
    </div>
  );
}

export function ControlBar({
  nav,
  summary,
  planAvailable,
}: {
  nav: DeviationNav;
  /** Last summary received (may belong to the previous comparison while refetching). */
  summary?: SummaryPayload;
  planAvailable: boolean;
}) {
  const { state } = nav;
  const lens = LENS_OF[state.cmp];
  const cmpId = useId();
  const periodId = useId();

  const comparisons = summary?.comparisons?.length
    ? summary.comparisons
    : CMPS.map((cmp) => ({ cmp, label: CMP_FALLBACK_LABEL[cmp], available: true, reason: undefined }));
  const groups: { label: string; lens: Lente }[] = [
    { label: "Plano", lens: "plano" },
    { label: "Previsão", lens: "previsao" },
  ];

  const periodValue = state.periodo ?? DEFAULT_PERIOD[state.cmp];
  const current = summary && summary.cmp === state.cmp ? summary.periods : null;
  const periods = current ?? [];
  const hasValue = periods.some((p) => p.code === periodValue);

  return (
    <div className="card flex flex-wrap items-end gap-x-6 gap-y-3 px-5 py-4">
      <Control label="Lente">
        <LensToggle value={lens} planAvailable={planAvailable} onChange={(l) => nav.setLens(l)} />
      </Control>

      <Control label="Comparação" htmlFor={cmpId}>
        <select
          id={cmpId}
          className="input w-auto max-w-full py-2 pr-9 text-[13px] font-medium"
          value={state.cmp}
          onChange={(e) => nav.setCmp(e.target.value as Cmp)}
        >
          {groups.map((g) => (
            <optgroup key={g.lens} label={g.label}>
              {comparisons
                .filter((c) => LENS_OF[c.cmp] === g.lens)
                .map((c) => (
                  <option key={c.cmp} value={c.cmp} disabled={!c.available && c.cmp !== state.cmp}>
                    {c.available ? c.label : `${c.label} — ${disabledSuffix(c.cmp, c.reason)}`}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      </Control>

      <Control label="Período" htmlFor={periodId}>
        <select
          id={periodId}
          className="input w-auto max-w-full py-2 pr-9 text-[13px] font-medium"
          value={periodValue}
          disabled={!current}
          onChange={(e) => nav.setPeriodo(e.target.value)}
        >
          {!current && <option value={periodValue}>Carregando períodos…</option>}
          {current && !hasValue && <option value={periodValue}>{periodValue}</option>}
          {periods.map((p) => (
            <option key={p.code} value={p.code}>
              {p.label}
            </option>
          ))}
        </select>
      </Control>

      {lens === "plano" ? (
        <Control label="Medida">
          <div role="group" aria-label="Medida">
            <Segmented<Medida>
              value={state.medida}
              options={[
                { value: "revenue", label: "Receita (R$)" },
                { value: "units", label: "Unidades" },
              ]}
              onChange={(m) => nav.setMedida(m)}
            />
          </div>
        </Control>
      ) : (
        <Control label="Medida">
          <span className="py-2 text-[12.5px] leading-snug text-muted">
            WMAPE em unidades · impacto em R$ ao preço realizado
          </span>
        </Control>
      )}
    </div>
  );
}
