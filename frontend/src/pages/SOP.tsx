import { useMutation } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  ChartLine,
  History,
  PiggyBank,
  Rocket,
  Scale,
  ShieldAlert,
  Target,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";

import { TimelineChart } from "../charts/TimelineChart";
import { DataTable } from "../components/DataTable";
import { FilterBar, useDimensions } from "../components/FilterBar";
import { ExportMenu, NoRunState } from "../components/RunControls";
import { Card, ClassBadge, ErrorState, Field, KpiCard, Loader, PageHeader } from "../components/ui";
import { useGet } from "../hooks/useApi";
import { useFilters } from "../hooks/useFilters";
import { CLASS_STYLE, SERIES } from "../lib/colors";
import { fmtMeasure, monthLabel, pct, shortMonth, type Measure } from "../lib/format";
import { api } from "../services/api";
import type { Feasibility, FeasibilityRow, TimelineRow } from "../types";

interface Cockpit {
  available: boolean;
  measure: Measure;
  horizon: string[];
  kpis: Record<string, number | null> & { bias_class?: string };
  timeline: TimelineRow[];
  quarters: {
    quarter: string;
    start: string;
    base: number;
    consensus: number;
    budget: number;
    target: number;
    gap_vs_budget: number;
  }[];
  risks: Record<string, any>[];
  opportunities: Record<string, any>[];
  feasibility_by_region: FeasibilityRow[];
  feasibility_by_channel: FeasibilityRow[];
  gap_by_customer: Record<string, any>[];
}

export default function SOP() {
  const { filters, measure } = useFilters();
  const { data, isLoading, error } = useGet<Cockpit>("/api/sop/cockpit", { ...filters, measure });
  const k = data?.kpis;
  const f = (v: number | null | undefined) => fmtMeasure(v, measure);
  return (
    <div>
      <PageHeader
        eyebrow="S&OP"
        title="S&OP Executive Cockpit"
        subtitle="Actual · Statistical forecast · Consensus · Budget · Sales target — gaps, risk, opportunity and target feasibility for the next 12 months."
        actions={<ExportMenu />}
      />
      <FilterBar />
      <ErrorState error={error} />
      {isLoading && <Loader />}
      {data && !data.available && <NoRunState />}
      {k && data?.available && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 2xl:grid-cols-8">
            <KpiCard
              label="Actual (LTM)"
              value={f(k.actual_ltm)}
              delta={pct(k.actual_growth, 1, true)}
              hint="YoY"
              icon={<History />}
              tone="navy"
            />
            <KpiCard
              label="Statistical 12M"
              value={f(k.statistical)}
              hint={`P10 ${f(k.p10)} · P90 ${f(k.p90)}`}
              icon={<ChartLine />}
            />
            <KpiCard
              label="Consensus 12M"
              value={f(k.consensus)}
              delta={pct(k.forecast_growth, 1, true)}
              hint={`vs LTM · events ${f(k.incremental)}`}
              icon={<Users />}
              tone="green"
            />
            <KpiCard label="Budget 12M" value={f(k.budget)} icon={<PiggyBank />} tone="orange" />
            <KpiCard label="Sales target 12M" value={f(k.target)} icon={<Target />} tone="yellow" />
            <KpiCard
              label="Gap vs budget"
              value={f(k.gap_vs_budget)}
              delta={pct(k.gap_vs_budget_pct, 1, true)}
              deltaTone={(k.gap_vs_budget ?? 0) >= 0 ? "good" : "bad"}
              hint={`vs target ${pct(k.gap_vs_target_pct, 1, true)}`}
              icon={<ArrowLeftRight />}
              tone="navy"
            />
            <KpiCard
              label="Risk"
              value={f(k.risk)}
              hint="Σ series below budget"
              icon={<ShieldAlert />}
              tone="red"
            />
            <KpiCard
              label="Opportunity"
              value={f(k.opportunity)}
              hint="Σ series above budget"
              icon={<Rocket />}
              tone="green"
            />
          </div>

          <div className="mt-5 grid gap-5 2xl:grid-cols-[1fr_420px]">
            <Card
              title="Demand plan"
              subtitle="24 months of actuals + 12-month horizon · shaded = P10–P90 statistical range"
            >
              <TimelineChart
                rows={data.timeline}
                measure={measure}
                lastActual={[...data.timeline].reverse().find((r) => r.actual != null)?.date}
                height={380}
              />
              <div className="mt-4 overflow-auto">
                <table className="table-base tabular">
                  <thead>
                    <tr>
                      <th>Quarter</th>
                      <th className="text-right">Statistical</th>
                      <th className="text-right">Consensus</th>
                      <th className="text-right">Budget</th>
                      <th className="text-right">Target</th>
                      <th className="text-right">Gap vs budget</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.quarters.map((q) => (
                      <tr key={q.quarter}>
                        <td>
                          {q.quarter} <span className="text-xs text-muted">from {shortMonth(q.start)}</span>
                        </td>
                        <td className="text-right">{f(q.base)}</td>
                        <td className="text-right font-medium">{f(q.consensus)}</td>
                        <td className="text-right">{f(q.budget)}</td>
                        <td className="text-right">{f(q.target)}</td>
                        <td
                          className={`text-right font-medium ${q.gap_vs_budget >= 0 ? "text-emerald-700" : "text-red-700"}`}
                        >
                          {f(q.gap_vs_budget)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            <FeasibilityPanel />
          </div>

          <div className="mt-5 grid gap-5 2xl:grid-cols-2">
            <FeasibilityTable
              title="Target feasibility by region"
              rows={data.feasibility_by_region}
              measure={measure}
            />
            <FeasibilityTable
              title="Target feasibility by channel"
              rows={data.feasibility_by_channel}
              measure={measure}
            />
          </div>

          <div className="mt-5 grid gap-5 2xl:grid-cols-2">
            <GapTable title="Top risks — consensus below budget" rows={data.risks} measure={measure} />
            <GapTable
              title="Top opportunities — consensus above budget"
              rows={data.opportunities}
              measure={measure}
            />
          </div>

          <GoalAllocation />
        </>
      )}
    </div>
  );
}

function FeasibilityPanel() {
  const { filters, measure } = useFilters();
  const { data: dims } = useDimensions();
  const [month, setMonth] = useState<string>("");
  const { data: a } = useGet<Feasibility>("/api/sop/feasibility", {
    ...filters,
    measure,
    months: month ? [month] : undefined,
  });
  const f = (v: number | null | undefined) => fmtMeasure(v, measure);
  if (!a?.available) return <Card title="Target feasibility">{a?.message ?? <Loader />}</Card>;
  const style = CLASS_STYLE[a.classification];
  const lo = Math.min(a.p10, a.target, a.budget) * 0.95;
  const hi = Math.max(a.p90, a.target, a.budget) * 1.03;
  const x = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
  return (
    <Card
      title="Is this target realistic?"
      subtitle="Probability from the consensus distribution (out-of-sample errors), growth, potential and planned events"
      actions={
        <select
          className="input w-auto py-1 text-xs"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          aria-label="Period"
        >
          <option value="">Next 12 months</option>
          {(dims?.horizon ?? []).map((m) => (
            <option key={m} value={m}>
              {monthLabel(m)}
            </option>
          ))}
        </select>
      }
    >
      <div className="flex items-center justify-between">
        <ClassBadge value={a.classification} large />
        <div className="text-right">
          <div className="text-3xl font-semibold" style={{ color: style?.color }}>
            {pct(a.probability, 0)}
          </div>
          <div className="text-[11px] text-muted">probability of reaching target</div>
        </div>
      </div>

      <div className="mt-6">
        <div className="relative h-14">
          <div
            className="absolute top-5 h-3 rounded-full bg-[rgba(42,120,214,0.18)]"
            style={{ left: x(a.p10), width: `calc(${x(a.p90)} - ${x(a.p10)})` }}
          />
          {[
            { v: a.p10, label: "P10", color: "#64748b" },
            { v: a.p50, label: "P50", color: SERIES.consensus },
            { v: a.p90, label: "P90", color: "#64748b" },
            { v: a.budget, label: "Budget", color: SERIES.budget },
            { v: a.target, label: "Target", color: "#b45309" },
          ].map((m, i) => (
            <div
              key={m.label}
              className="absolute top-0 -translate-x-1/2 text-center"
              style={{ left: x(m.v) }}
            >
              <div className={`text-[10px] font-semibold ${i % 2 ? "mt-9" : ""}`} style={{ color: m.color }}>
                {m.label}
              </div>
              <div
                className="mx-auto h-5 w-0.5"
                style={{ background: m.color, marginTop: i % 2 ? -36 : 2 }}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-x-4 gap-y-2.5 text-sm">
        <Row label="Target" value={f(a.target)} />
        <Row label="Consensus (P50)" value={f(a.consensus)} />
        <Row label="P10 – P90" value={`${f(a.p10)} – ${f(a.p90)}`} />
        <Row label="Budget" value={f(a.budget)} />
        <Row label="Required growth vs LY" value={pct(a.required_growth, 1, true)} />
        <Row label="Forecast growth vs LY" value={pct(a.forecast_growth, 1, true)} />
        <Row label="Historical growth (LTM)" value={pct(a.historical_growth, 1, true)} />
        <Row label="Planned events" value={f(a.planned_events)} />
      </div>

      <div className="mt-5 rounded-lg border border-line bg-slate-50/70 p-3">
        <div className="label-xs mb-1.5 flex items-center gap-1.5">
          <Scale size={12} /> Target calibration
        </div>
        <div className="text-sm">
          Target vs budget: <b>{pct(a.calibration.required_incremental_vs_budget, 1, true)}</b> required
          incremental growth.
          <br />
          Gap vs consensus: <b>{f(a.calibration.gap_vs_consensus)}</b> (
          {pct(a.calibration.gap_vs_consensus_pct, 1, true)}).
        </div>
      </div>

      <ul className="mt-4 space-y-1.5 text-xs text-ink-2">
        {a.reasons.map((r) => (
          <li key={r}>• {r}</li>
        ))}
      </ul>
      {a.levers.length > 0 && (
        <div className="mt-4">
          <div className="label-xs mb-1.5">Lever that would close the gap on its own</div>
          <table className="table-base text-xs">
            <tbody>
              {a.levers.map((l) => (
                <tr key={l.lever}>
                  <td className="font-medium">{l.lever}</td>
                  <td className="text-right tabular">
                    {l.required_change == null
                      ? "—"
                      : l.lever === "Promotions"
                        ? `${l.required_change.toFixed(1)} months`
                        : pct(l.required_change, 1, true)}
                  </td>
                  <td className="text-right">
                    {l.plausible ? (
                      <span className="text-emerald-700">plausible</span>
                    ) : (
                      <span className="text-red-700">unrealistic</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-4 rounded-lg p-3 text-sm" style={{ background: `${style?.color}14` }}>
        {a.recommendation}
      </p>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] text-muted">{label}</div>
      <div className="font-semibold tabular">{value}</div>
    </div>
  );
}

function FeasibilityTable({
  title,
  rows,
  measure,
}: {
  title: string;
  rows: FeasibilityRow[];
  measure: Measure;
}) {
  const f = (v: number | null | undefined) => fmtMeasure(v, measure);
  return (
    <Card title={title} subtitle="Target vs consensus distribution per member">
      <DataTable
        rows={rows}
        rowKey={(r) => r.member}
        initialSort={{ key: "probability", dir: "asc" }}
        columns={[
          { key: "member", label: "Member", render: (r) => <span className="font-medium">{r.member}</span> },
          { key: "target", label: "Target", align: "right", render: (r) => f(r.target) },
          { key: "consensus", label: "Consensus", align: "right", render: (r) => f(r.consensus) },
          { key: "p90", label: "P90", align: "right", render: (r) => f(r.p90) },
          { key: "gap_vs_target_pct", label: "Gap", align: "right", format: "percent_signed" },
          { key: "probability", label: "Probability", align: "right", format: "percent" },
          { key: "classification", label: "Class", render: (r) => <ClassBadge value={r.classification} /> },
        ]}
      />
    </Card>
  );
}

function GapTable({
  title,
  rows,
  measure,
}: {
  title: string;
  rows: Record<string, any>[];
  measure: Measure;
}) {
  const f = (v: number | null | undefined) => fmtMeasure(v, measure);
  return (
    <Card title={title}>
      <DataTable
        rows={rows}
        rowKey={(r) => r.key}
        maxHeight={360}
        columns={[
          { key: "customer", label: "Customer" },
          { key: "product", label: "SKU", render: (r) => `${r.sku} · ${r.product}` },
          {
            key: "series_type",
            label: "Type",
            render: (r) => <span className="text-xs text-muted">{r.series_type}</span>,
          },
          { key: "consensus", label: "Consensus", align: "right", render: (r) => f(r.consensus) },
          { key: "budget", label: "Budget", align: "right", render: (r) => f(r.budget) },
          {
            key: "gap",
            label: "Gap",
            align: "right",
            render: (r) => (
              <span className={r.gap >= 0 ? "text-emerald-700" : "text-red-700"}>{f(r.gap)}</span>
            ),
          },
          { key: "gap_pct", label: "%", align: "right", format: "percent_signed" },
        ]}
      />
    </Card>
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

function GoalAllocation() {
  const { filters, measure } = useFilters();
  const [dimension, setDimension] = useState("region");
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
  const f = (v: number | null | undefined) => fmtMeasure(v, measure);
  return (
    <Card
      className="mt-5"
      title="Goal allocation"
      subtitle="Distribute a total target by region, channel, customer, category or SKU — historical, potential, forecast-based or strategic weights"
    >
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Allocate by">
          <select className="input w-40" value={dimension} onChange={(e) => setDimension(e.target.value)}>
            {["region", "channel", "customer", "category", "sku"].map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Method">
          <select className="input w-56" value={method} onChange={(e) => setMethod(e.target.value)}>
            <option value="historical">Historical weight (last 12 months)</option>
            <option value="potential">Potential based (growth headroom)</option>
            <option value="forecast">Forecast based (consensus)</option>
            <option value="strategic">Strategic (user weights)</option>
          </select>
        </Field>
        <Field
          label={`Total target (${measure === "revenue" ? "R$" : "units"})`}
          hint={`Leave empty to use the current target ${data ? f(data.total_target) : ""}`}
        >
          <input
            className="input w-48"
            type="number"
            placeholder="current target"
            value={total}
            onChange={(e) => setTotal(e.target.value)}
          />
        </Field>
        <button type="button" className="btn-primary mb-5" onClick={() => alloc.mutate()}>
          Allocate
        </button>
      </div>
      <ErrorState error={alloc.error} />
      {data && (
        <DataTable
          rows={data.rows}
          rowKey={(r) => r.member}
          maxHeight={420}
          columns={[
            {
              key: "member",
              label: dimension,
              render: (r) => <span className="font-medium">{r.member}</span>,
            },
            {
              key: "weight",
              label: method === "strategic" ? "Weight (edit)" : "Weight",
              align: "right",
              render: (r) =>
                method === "strategic" ? (
                  <input
                    className="input w-20 py-1 text-right text-xs"
                    type="number"
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
              label: "Allocated target",
              align: "right",
              render: (r) => <b>{f(r.allocated_target)}</b>,
            },
            {
              key: "current_target",
              label: "Current target",
              align: "right",
              render: (r) => f(r.current_target),
            },
            { key: "consensus", label: "Consensus", align: "right", render: (r) => f(r.consensus) },
            { key: "gap_pct", label: "Gap", align: "right", format: "percent_signed" },
            { key: "required_growth", label: "Req. growth vs LTM", align: "right", format: "percent_signed" },
            { key: "probability", label: "Probability", align: "right", format: "percent" },
            {
              key: "classification",
              label: "Feasibility",
              render: (r) => <ClassBadge value={r.classification} />,
            },
          ]}
        />
      )}
    </Card>
  );
}
