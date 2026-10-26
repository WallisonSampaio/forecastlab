/**
 * Goal allocation: splits a total target by region, channel, customer, category or SKU.
 * Moved from pages/SOP.tsx (spec §3, F6 day 0); the Cenários page shows it as a tab.
 */
import { useMutation } from "@tanstack/react-query";
import { Split } from "lucide-react";
import { useEffect, useState } from "react";

import { useFilters } from "../hooks/useFilters";
import { CLASS_STYLE } from "../lib/colors";
import { fmtMeasure, pct } from "../lib/format";
import { t } from "../lib/labels";
import { api } from "../services/api";
import { DataTable } from "./DataTable";
import { Card, ClassBadge, ErrorState, Field, ProgressBar } from "./ui";

type Fmt = (v: number | null | undefined) => string;

/** Probability bar + percentage, coloured by the feasibility class. */
export function ProbabilityCell({ p, cls }: { p: number; cls: string }) {
  const color = CLASS_STYLE[cls]?.color ?? "#3483fa";
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="w-14">
        <ProgressBar value={p} color={color} />
      </div>
      <span className="w-10 text-right font-semibold text-ink">{pct(p, 0)}</span>
    </div>
  );
}

interface Allocation {
  dimension: string;
  method: string;
  total_target: number;
  rows: {
    member: string;
    weight: number;
    allocated_target: number;
    consensus: number;
    actual_ltm: number;
    current_target: number;
    gap: number;
    gap_pct: number | null;
    required_growth: number | null;
    probability: number;
    classification: string;
  }[];
}

const ALLOC_DIMS = ["region", "channel", "customer", "category", "sku"] as const;

const ALLOC_METHODS = [
  { value: "historical", label: "Peso histórico (últimos 12 meses)" },
  { value: "potential", label: "Baseado em potencial (headroom)" },
  { value: "forecast", label: "Baseado no forecast (consenso)" },
  { value: "strategic", label: "Estratégico (pesos do usuário)" },
];

export function GoalAllocation({ className }: { className?: string }) {
  const { filters, measure } = useFilters();
  const [dimension, setDimension] = useState<string>("region");
  const [method, setMethod] = useState("historical");
  const [total, setTotal] = useState<string>("");
  const [weights, setWeights] = useState<Record<string, number>>({});
  const alloc = useMutation({
    mutationFn: () =>
      api.post<Allocation>("/api/sop/allocation", {
        dimension,
        method,
        measure,
        filters,
        total_target: total ? Number(total) : null,
        weights: method === "strategic" ? weights : null,
      }),
  });
  const { mutate } = alloc;
  useEffect(() => {
    mutate();
  }, [dimension, method, measure, filters, mutate]);
  const data = alloc.data;
  const f: Fmt = (v) => fmtMeasure(v, measure);
  const strategic = method === "strategic";
  return (
    <Card
      className={className}
      title="Alocação de metas"
      subtitle="Distribua uma meta total por região, canal, cliente, categoria ou SKU — por peso histórico, potencial, forecast ou pesos estratégicos"
      icon={<Split />}
      tone="navy"
    >
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Alocar por">
          <select className="input w-44" value={dimension} onChange={(e) => setDimension(e.target.value)}>
            {ALLOC_DIMS.map((d) => (
              <option key={d} value={d}>
                {t.dimension(d)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Método">
          <select className="input w-72" value={method} onChange={(e) => setMethod(e.target.value)}>
            {ALLOC_METHODS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label={`Meta total (${measure === "revenue" ? "R$" : "unidades"})`}>
          <input
            className="input w-52"
            type="number"
            min={0}
            placeholder="meta atual"
            value={total}
            onChange={(e) => setTotal(e.target.value)}
          />
        </Field>
        <button
          type="button"
          className="btn-primary"
          onClick={() => alloc.mutate()}
          disabled={alloc.isPending}
        >
          <Split size={16} /> Alocar
        </button>
      </div>
      <p className="mt-2 text-xs text-muted">
        Deixe a meta total em branco para usar a meta atual
        {data ? (
          <>
            {" "}
            (<b className="text-ink-2">{f(data.total_target)}</b>)
          </>
        ) : null}
        .{strategic && " No modo estratégico, edite os pesos (%) na tabela e clique em Alocar."}
      </p>
      <ErrorState error={alloc.error} />
      {data && (
        <div className="mt-4">
          <DataTable
            rows={data.rows}
            rowKey={(r) => r.member}
            maxHeight={420}
            columns={[
              {
                key: "member",
                label: t.dimension(dimension),
                render: (r) => <span className="font-semibold text-ink">{r.member}</span>,
              },
              {
                key: "weight",
                label: strategic ? "Peso (editável)" : "Peso",
                align: "right",
                render: (r) =>
                  strategic ? (
                    <input
                      className="input w-20 py-1 text-right text-xs"
                      type="number"
                      aria-label={`Peso de ${r.member}`}
                      value={weights[r.member] ?? Math.round(r.weight * 100)}
                      onChange={(e) => setWeights({ ...weights, [r.member]: Number(e.target.value) })}
                      onClick={(e) => e.stopPropagation()}
                    />
                  ) : (
                    pct(r.weight)
                  ),
              },
              {
                key: "allocated_target",
                label: "Meta alocada",
                align: "right",
                render: (r) => <b className="text-ink">{f(r.allocated_target)}</b>,
              },
              {
                key: "current_target",
                label: "Meta atual",
                align: "right",
                render: (r) => f(r.current_target),
              },
              { key: "consensus", label: "Consenso", align: "right", render: (r) => f(r.consensus) },
              { key: "gap_pct", label: "Gap", align: "right", format: "percent_signed" },
              {
                key: "required_growth",
                label: "Cresc. exigido vs U12M",
                align: "right",
                format: "percent_signed",
              },
              {
                key: "probability",
                label: "Probabilidade",
                align: "right",
                render: (r) => <ProbabilityCell p={r.probability} cls={r.classification} />,
              },
              {
                key: "classification",
                label: "Viabilidade",
                render: (r) => <ClassBadge value={r.classification} />,
              },
            ]}
          />
        </div>
      )}
    </Card>
  );
}
