import { ArrowRight, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";

import { BarChart, SimpleLineChart } from "../charts/BasicCharts";
import { DataTable } from "../components/DataTable";
import { FilterBar } from "../components/FilterBar";
import { NoRunState } from "../components/RunControls";
import { Badge, Card, KpiCard, Loader, PageHeader, Segmented } from "../components/ui";
import { useGet } from "../hooks/useApi";
import { useFilters } from "../hooks/useFilters";
import { SERIES, STATUS } from "../lib/colors";
import { full, monthLabel, pct, shortMonth } from "../lib/format";

interface Group {
  overrides: number;
  improved_pct: number;
  wmape_statistical: number;
  wmape_consensus: number;
  fva_pp: number;
  fva_units: number;
  avg_adjustment: number;
  [k: string]: any;
}

interface FvaData {
  available: boolean;
  message?: string;
  stairstep: {
    naive: number;
    statistical: number;
    consensus: number;
    fva_statistical_vs_naive: number;
    fva_consensus_vs_statistical: number;
  };
  monthly: { date: string; naive: number; statistical: number; consensus: number }[];
  cells_evaluated: number;
  pending_overrides: number;
  summary: {
    overrides: number;
    improved?: number;
    worsened?: number;
    neutral?: number;
    value_added_pct?: number;
    wmape_statistical_overridden?: number;
    wmape_consensus_overridden?: number;
    fva_pp_overridden?: number;
    fva_units?: number;
  };
  by_planner: Group[];
  by_event_type: Group[];
  by_direction: Group[];
  by_magnitude: Group[];
  by_customer?: Group[];
  overrides: Record<string, any>[];
  examples: Record<string, any>[];
}

type GroupKey = "planner" | "event_type" | "direction" | "magnitude";

export default function FVA() {
  const { filters } = useFilters();
  const { data, isLoading } = useGet<FvaData>("/api/fva", filters);
  const [group, setGroup] = useState<GroupKey>("event_type");
  if (isLoading) return <Loader />;
  if (!data?.available) return <NoRunState />;
  const s = data.summary;
  const st = data.stairstep;
  const groups: Record<GroupKey, Group[]> = {
    planner: data.by_planner,
    event_type: data.by_event_type,
    direction: data.by_direction,
    magnitude: data.by_magnitude,
  };
  const rows = groups[group] ?? [];
  return (
    <div>
      <PageHeader
        eyebrow="Forecast Value Added"
        title="Do human overrides improve the forecast?"
        subtitle="Naive → Statistical (champion, out-of-sample) → Consensus (after planner overrides), compared cell by cell over the last 12 months."
      />
      <FilterBar showMeasure={false} />
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <KpiCard
          label="Overrides adding value"
          value={pct(s.value_added_pct, 0)}
          hint={`${s.improved ?? 0} improved · ${s.worsened ?? 0} worsened · ${s.neutral ?? 0} neutral`}
          accent={STATUS.good}
        />
        <KpiCard
          label="FVA of overrides"
          value={`${pct(s.fva_pp_overridden, 1, true)}`}
          deltaTone={(s.fva_pp_overridden ?? 0) >= 0 ? "good" : "bad"}
          delta="WMAPE points on overridden cells"
          hint={`${pct(s.wmape_statistical_overridden)} → ${pct(s.wmape_consensus_overridden)}`}
        />
        <KpiCard
          label="FVA statistical vs naive"
          value={pct(st.fva_statistical_vs_naive, 1, true)}
          hint={`naive ${pct(st.naive)} → statistical ${pct(st.statistical)}`}
          accent={SERIES.base}
        />
        <KpiCard
          label="Overrides evaluated"
          value={full(s.overrides)}
          hint={`${full(data.cells_evaluated)} cells · ${data.pending_overrides} pending (future)`}
        />
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Card title="FVA stairstep" subtitle="WMAPE at each step of the process (lower is better)">
          <BarChart
            categories={["Naive", "Statistical", "Consensus"]}
            series={[{ name: "WMAPE", data: [st.naive, st.statistical, st.consensus] }]}
            format="percent"
            height={280}
            highlight={2}
          />
          <div className="mt-2 flex items-center justify-center gap-3 text-sm">
            <span>{pct(st.naive)}</span>
            <ArrowRight size={14} className="text-muted" />
            <span className="font-semibold text-[#2a78d6]">{pct(st.statistical)}</span>
            <ArrowRight size={14} className="text-muted" />
            <span className="font-semibold text-emerald-700">{pct(st.consensus)}</span>
          </div>
        </Card>
        <Card title="Monthly WMAPE by step" subtitle="Backtest months">
          <SimpleLineChart
            categories={data.monthly.map((m) => shortMonth(m.date))}
            series={[
              { name: "Naive", data: data.monthly.map((m) => m.naive), color: "#94a3b8", dashed: true },
              { name: "Statistical", data: data.monthly.map((m) => m.statistical), color: SERIES.base },
              { name: "Consensus", data: data.monthly.map((m) => m.consensus), color: SERIES.consensus },
            ]}
            format="percent"
            height={300}
          />
        </Card>
      </div>

      {data.examples?.length > 0 && (
        <div className="mt-5 grid gap-5 md:grid-cols-2">
          {data.examples.map((e) => (
            <div
              key={e.kind}
              className={`card p-5 ${e.kind === "worst" ? "border-red-200" : "border-emerald-200"}`}
            >
              <div className="flex items-center gap-2">
                {e.kind === "worst" ? (
                  <ThumbsDown size={16} className="text-red-600" />
                ) : (
                  <ThumbsUp size={16} className="text-emerald-600" />
                )}
                <span className="label-xs">
                  {e.kind === "worst"
                    ? "Override that destroyed most value"
                    : "Override that added most value"}
                </span>
              </div>
              <div className="mt-2 text-sm text-ink-2">
                {e.customer} · {e.sku} · {monthLabel(e.date)} · {e.event_type} by {e.planner}
              </div>
              <div className="mt-3 grid grid-cols-3 gap-3 text-center">
                <div className="rounded-lg bg-slate-50 p-2">
                  <div className="text-[11px] text-muted">Statistical</div>
                  <div className="text-lg font-semibold">{full(e.statistical)}</div>
                </div>
                <div className="rounded-lg bg-slate-50 p-2">
                  <div className="text-[11px] text-muted">Planner override</div>
                  <div className="text-lg font-semibold">{full(e.consensus)}</div>
                </div>
                <div className="rounded-lg bg-slate-50 p-2">
                  <div className="text-[11px] text-muted">Actual</div>
                  <div className="text-lg font-semibold">{full(e.actual)}</div>
                </div>
              </div>
              <div
                className={`mt-3 text-sm font-semibold ${e.kind === "worst" ? "text-red-700" : "text-emerald-700"}`}
              >
                {e.message}
              </div>
            </div>
          ))}
        </div>
      )}

      <Card
        className="mt-5"
        title="Value added by group"
        subtitle="FVA = WMAPE(statistical) − WMAPE(consensus) on the overridden cells, in WMAPE points"
        actions={
          <Segmented<GroupKey>
            size="xs"
            value={group}
            onChange={setGroup}
            options={[
              { value: "event_type", label: "Event type" },
              { value: "planner", label: "Planner" },
              { value: "direction", label: "Direction" },
              { value: "magnitude", label: "Magnitude" },
            ]}
          />
        }
      >
        <div className="grid gap-5 xl:grid-cols-2">
          <BarChart
            categories={rows.map((r) => String(r[group]))}
            series={[{ name: "FVA (pts)", data: rows.map((r) => r.fva_pp) }]}
            signColors={{ positive: STATUS.good, negative: STATUS.critical }}
            horizontal
            format="percent_signed"
            height={Math.max(220, rows.length * 34 + 40)}
          />
          <DataTable
            rows={rows}
            rowKey={(r) => String(r[group])}
            maxHeight={360}
            columns={[
              { key: group, label: group.replace("_", " ") },
              { key: "overrides", label: "Overrides", align: "right", format: "number" },
              { key: "improved_pct", label: "% improved", align: "right", format: "percent" },
              { key: "avg_adjustment", label: "Avg adj.", align: "right", format: "percent_signed" },
              { key: "wmape_statistical", label: "WMAPE stat", align: "right", format: "percent" },
              { key: "wmape_consensus", label: "WMAPE cons.", align: "right", format: "percent" },
              { key: "fva_pp", label: "FVA", align: "right", format: "percent_signed" },
            ]}
          />
        </div>
      </Card>

      <Card
        className="mt-5"
        title="Override log"
        subtitle="Every historical override with its outcome — sorted from most value destroyed to most value added"
      >
        <DataTable
          rows={data.overrides}
          searchable
          searchKeys={["customer", "sku", "planner", "event_type", "outcome", "comment"]}
          maxHeight={520}
          dense
          columns={[
            { key: "date", label: "Month", render: (r) => String(r.date).slice(0, 7) },
            { key: "customer", label: "Customer" },
            { key: "sku", label: "SKU" },
            { key: "planner", label: "Planner" },
            { key: "event_type", label: "Event" },
            {
              key: "comment",
              label: "Comment",
              render: (r) => <span className="wrap text-xs text-muted">{r.comment}</span>,
            },
            { key: "adjustment_pct", label: "Adj.", align: "right", format: "percent_signed" },
            { key: "statistical", label: "Statistical", align: "right", format: "number" },
            { key: "consensus", label: "Override", align: "right", format: "number" },
            { key: "actual", label: "Actual", align: "right", format: "number" },
            { key: "fva_units", label: "FVA units", align: "right", format: "number" },
            {
              key: "outcome",
              label: "Outcome",
              render: (r) => (
                <Badge
                  className={
                    r.outcome === "Improved"
                      ? "bg-emerald-50 text-emerald-800"
                      : r.outcome === "Worsened"
                        ? "bg-red-50 text-red-800"
                        : "bg-slate-100 text-slate-700"
                  }
                >
                  {r.outcome}
                </Badge>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
