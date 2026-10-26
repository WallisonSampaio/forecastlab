import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { MessageSquareText, Plus } from "lucide-react";
import { useState } from "react";

import { useGet } from "../hooks/useApi";
import { monthLabel, pct } from "../lib/format";
import { t } from "../lib/labels";
import { api } from "../services/api";
import { ErrorState, Field } from "./ui";

interface LibraryEvent {
  type: string;
  typical_uplift: number;
  description: string;
}

export interface OverrideFormDefaults {
  /** Horizon month, "YYYY-MM-DD" (a "YYYY-MM" prefix is also matched). */
  date?: string;
  /** Event type of the library ("Promoção", "Merchandising", …). */
  event_type?: string;
  /** Fraction: 0.2 = +20%. */
  uplift_pct?: number;
  comment?: string;
}

export interface OverrideFormProps {
  customer: string;
  /** null/undefined: the adjustment applies to every SKU of the customer. */
  sku?: string | null;
  /** Selectable months (forecast horizon), "YYYY-MM-DD". */
  horizon: string[];
  /** Prefill (e.g. from the deep dive's "Criar ajuste comercial"); read on mount. */
  defaults?: OverrideFormDefaults;
  /** Called after the adjustment is saved and every query was invalidated. */
  onSaved?: () => void;
}

/** "12,5" for 0.125; integers without decimals. */
const percentText = (fraction: number) => {
  const v = Math.round(fraction * 1000) / 10;
  return Number.isInteger(v) ? String(v) : String(v).replace(".", ",");
};

/**
 * Commercial adjustment (override) form: month, event, expected uplift, scope and comment.
 * Posts `/api/overrides` and invalidates every query (the consensus changes everywhere).
 */
export function OverrideForm({ customer, sku, horizon, defaults, onSaved }: OverrideFormProps) {
  const qc = useQueryClient();
  const { data: library } = useGet<LibraryEvent[]>("/api/overrides/event-library");
  const [form, setForm] = useState<{
    date: string;
    event_type: string;
    /** Raw text of the uplift field, so "-", "-1" or "12,5" can be typed; null = event default. */
    uplift: string | null;
    comment: string;
    scope: "series" | "customer";
  }>(() => ({
    date: defaults?.date ?? "",
    event_type: defaults?.event_type ?? "",
    uplift: defaults?.uplift_pct != null ? percentText(defaults.uplift_pct) : null,
    comment: defaults?.comment ?? "",
    scope: sku ? "series" : "customer",
  }));

  // Effective values: fall back to the first horizon month / first library event.
  const date =
    (form.date && horizon.find((m) => m === form.date || m.startsWith(form.date))) || (horizon[0] ?? "");
  // Tolerant match: a prefill may carry the English code of an older library ("Promotion").
  const event =
    library?.find((l) => l.type === form.event_type) ??
    library?.find((l) => !!form.event_type && t.event(l.type) === t.event(form.event_type)) ??
    library?.[0];
  const eventType = event?.type ?? "";
  const defaultUplift = String(Math.round((event?.typical_uplift ?? 0.15) * 100));
  const upliftText = form.uplift ?? defaultUplift;
  const uplift = Number(upliftText.trim().replace(",", "."));
  const upliftValid = upliftText.trim() !== "" && Number.isFinite(uplift) && uplift >= -100 && uplift <= 500;
  const scope = sku ? form.scope : "customer";

  const create = useMutation({
    mutationFn: () =>
      api.post("/api/overrides", {
        customer,
        sku: scope === "series" ? sku : null,
        date,
        event_type: eventType,
        uplift_pct: uplift / 100,
        comment: form.comment,
        created_by: "Planejador de Demanda",
      }),
    onSuccess: () => {
      setForm((f) => ({ ...f, comment: "" }));
      qc.invalidateQueries();
      onSaved?.();
    },
  });

  return (
    <div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Mês">
          <select className="input" value={date} onChange={(e) => setForm({ ...form, date: e.target.value })}>
            {horizon.map((m) => (
              <option key={m} value={m}>
                {monthLabel(m, "long")}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label="Evento"
          hint={
            event ? `${event.description} · uplift típico ${pct(event.typical_uplift, 0, true)}` : undefined
          }
        >
          <select
            className="input"
            value={eventType}
            onChange={(e) => {
              const ev = library?.find((l) => l.type === e.target.value);
              setForm({
                ...form,
                event_type: e.target.value,
                uplift: ev ? String(Math.round(ev.typical_uplift * 100)) : form.uplift,
              });
            }}
          >
            {(library ?? []).map((l) => (
              <option key={l.type} value={l.type}>
                {t.event(l.type)}
              </option>
            ))}
          </select>
        </Field>
        <Field
          label="Uplift esperado (%)"
          hint={
            upliftValid ? undefined : (
              <span className="text-red-600">Informe um número entre -100 e 500 (ex.: 15 ou -10).</span>
            )
          }
        >
          <input
            className={clsx("input tabular", !upliftValid && "border-red-300")}
            type="text"
            inputMode="decimal"
            value={upliftText}
            aria-invalid={!upliftValid}
            onChange={(e) => setForm({ ...form, uplift: e.target.value })}
          />
        </Field>
        <Field label="Aplica-se a">
          <select
            className="input"
            value={scope}
            disabled={!sku}
            onChange={(e) => setForm({ ...form, scope: e.target.value as "series" | "customer" })}
          >
            {sku && <option value="series">Este SKU neste cliente</option>}
            <option value="customer">Todos os SKUs de {customer}</option>
          </select>
        </Field>
      </div>
      <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="min-w-0 flex-1">
          <Field label="Comentário">
            <span className="relative block">
              <MessageSquareText
                size={15}
                className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted"
              />
              <input
                className="input pl-9"
                placeholder="Ex.: nova campanha de merchandising no ponto de venda"
                value={form.comment}
                onChange={(e) => setForm({ ...form, comment: e.target.value })}
              />
            </span>
          </Field>
        </div>
        <button
          type="button"
          className="btn-primary shrink-0"
          onClick={() => create.mutate()}
          disabled={create.isPending || !date || !eventType || !upliftValid}
        >
          <Plus size={16} /> Adicionar ajuste
        </button>
      </div>
      <div className="mt-3 empty:hidden">
        <ErrorState error={create.error} />
      </div>
    </div>
  );
}
