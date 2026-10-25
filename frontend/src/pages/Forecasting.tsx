import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ChartLine,
  ChevronRight,
  Crosshair,
  GitBranch,
  History,
  LineChart,
  PiggyBank,
  Plus,
  Search,
  Trash2,
  Trophy,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { BarChart, SimpleLineChart } from "../charts/BasicCharts";
import { TimelineChart } from "../charts/TimelineChart";
import { DataTable } from "../components/DataTable";
import { FilterBar, useDimensions } from "../components/FilterBar";
import { NoRunState, RunForecastButton } from "../components/RunControls";
import {
  Badge,
  BiasBadge,
  Card,
  ConfidenceBadge,
  ErrorState,
  Field,
  KpiCard,
  Loader,
  PageHeader,
  Segmented,
  Tabs,
} from "../components/ui";
import { useGet } from "../hooks/useApi";
import { useFilters, type FilterDim } from "../hooks/useFilters";
import { SERIES } from "../lib/colors";
import { fmtMeasure, monthLabel, pct, shortMonth, units, type Measure } from "../lib/format";
import { api } from "../services/api";
import type { LeaderRow, Override, SeriesRow, TimelineRow, Totals } from "../types";

type Mode = "series" | "hierarchy";

export default function Forecasting() {
  const [params, setParams] = useSearchParams();
  const mode = (params.get("mode") as Mode) ?? "series";
  return (
    <div>
      <PageHeader
        eyebrow="Forecasting"
        title="Forecast Workspace"
        subtitle="Statistical base forecast (champion model, P10–P90) separated from the consensus forecast (base + commercial events)."
        actions={<RunForecastButton />}
      />
      <Tabs<Mode>
        value={mode}
        onChange={(m) => setParams({ mode: m })}
        tabs={[
          { value: "series", label: "Series workspace", icon: <LineChart size={15} /> },
          { value: "hierarchy", label: "Hierarchy explorer", icon: <GitBranch size={15} /> },
        ]}
      />
      <div className="mt-5">{mode === "series" ? <SeriesWorkspace /> : <HierarchyExplorer />}</div>
    </div>
  );
}

interface Detail {
  series_id: string;
  has_run: boolean;
  header: Record<string, any>;
  timeline: TimelineRow[];
  selection?: {
    series_type: string;
    classification_reason: string;
    champion: string;
    challenger: string | null;
    wmape: number;
    accuracy: number;
    bias: number;
    bias_class: string;
    challenger_wmape: number | null;
    confidence: string;
    confidence_score: number;
    stability: number | null;
    history_months: number;
    candidates: string[];
  };
  next_month?: { date: string; base: number; consensus: number; p10: number; p90: number };
  totals?: Totals;
  leaderboard?: LeaderRow[];
  backtest?: {
    model: string;
    fold: number;
    date: string;
    horizon_step: number;
    actual: number;
    forecast: number;
  }[];
  overrides?: Override[];
  baseline_vs_incremental?: { date: string; p50: number; incremental: number; consensus: number }[];
}

function SeriesWorkspace() {
  const [params, setParams] = useSearchParams();
  const { filters, measure, setMeasure } = useFilters();
  const { data: list, isLoading } = useGet<SeriesRow[]>("/api/forecast/series", filters);
  const [q, setQ] = useState("");
  const selected = params.get("series") ?? list?.[0]?.series_id ?? null;
  const { data: d, error } = useGet<Detail>(selected ? "/api/forecast/series-detail" : null, {
    series_id: selected ?? undefined,
    measure,
  });
  const filtered = useMemo(() => {
    const needle = q.toLowerCase();
    return (list ?? []).filter(
      (s) => !needle || `${s.customer} ${s.sku} ${s.product} ${s.series_type}`.toLowerCase().includes(needle),
    );
  }, [list, q]);

  if (isLoading) return <Loader />;
  return (
    <div>
      <FilterBar showMeasure={false} />
      <div className="grid gap-5 xl:grid-cols-[300px_1fr]">
        <div className="card flex max-h-[calc(100vh-220px)] flex-col overflow-hidden xl:sticky xl:top-20">
          <div className="border-b border-line p-3">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <input
                className="input pl-8"
                placeholder="Search customer, SKU, type…"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </div>
            <div className="mt-2 text-[11px] text-muted">{filtered.length} series · sorted by revenue</div>
          </div>
          <ul className="flex-1 overflow-auto">
            {filtered.map((s) => (
              <li key={s.series_id}>
                <button
                  type="button"
                  onClick={() => setParams({ mode: "series", series: s.series_id })}
                  className={clsx(
                    "w-full border-b border-slate-100 px-3 py-2.5 text-left transition hover:bg-slate-50",
                    s.series_id === selected && "bg-blue-50/80 hover:bg-blue-50",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-[13px] font-semibold">{s.sku}</span>
                    <span className="text-[11px] tabular text-muted">
                      {s.wmape != null ? `WMAPE ${pct(s.wmape, 0)}` : ""}
                    </span>
                  </div>
                  <div className="truncate text-xs text-ink-2">{s.product}</div>
                  <div className="mt-0.5 flex items-center justify-between gap-2">
                    <span className="truncate text-[11px] text-muted">{s.customer}</span>
                    {s.series_type && (
                      <span className="shrink-0 text-[10px] font-medium text-blue-700">{s.series_type}</span>
                    )}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="min-w-0">
          <ErrorState error={error} />
          {d && !d.has_run && <NoRunState />}
          {d?.selection && (
            <>
              <SeriesHeader d={d} measure={measure} setMeasure={setMeasure} />
              <div className="mt-5 grid gap-5 2xl:grid-cols-[1fr_340px]">
                <Card
                  title="Actual · Base Forecast · Consensus · Budget · Target · P10–P90"
                  subtitle="Toggle series in the legend · dotted lines (hidden by default): challenger and out-of-sample backtest"
                >
                  <TimelineChart
                    rows={d.timeline}
                    measure={measure}
                    lastActual={lastActual(d.timeline)}
                    height={380}
                  />
                </Card>
                <ChampionCard d={d} />
              </div>
              <div className="mt-5 grid gap-5 2xl:grid-cols-2">
                <Leaderboard rows={d.leaderboard ?? []} />
                <BacktestCard d={d} />
              </div>
              <div className="mt-5 grid gap-5 2xl:grid-cols-[1fr_1fr]">
                <OverridesCard d={d} />
                <Card
                  title="Baseline vs incremental"
                  subtitle="Baseline demand + incremental demand (events) = consensus forecast"
                >
                  <BarChart
                    categories={(d.baseline_vs_incremental ?? []).map((r) => shortMonth(r.date))}
                    series={[
                      {
                        name: "Baseline (statistical)",
                        data: (d.baseline_vs_incremental ?? []).map((r) => r.p50),
                        color: SERIES.base,
                      },
                      {
                        name: "Incremental (events)",
                        data: (d.baseline_vs_incremental ?? []).map((r) => r.incremental),
                        color: SERIES.consensus,
                      },
                    ]}
                    stacked
                    format={measure === "revenue" ? "currency" : "units"}
                    height={300}
                  />
                </Card>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

const lastActual = (rows: TimelineRow[]) => [...rows].reverse().find((r) => r.actual != null)?.date;

function SeriesHeader({
  d,
  measure,
  setMeasure,
}: {
  d: Detail;
  measure: Measure;
  setMeasure: (m: Measure) => void;
}) {
  const h = d.header;
  const s = d.selection!;
  const n = d.next_month;
  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line bg-gradient-to-r from-slate-50 to-white px-5 py-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-muted">{h.sku}</span>
            <Badge className="bg-blue-50 text-blue-800">{s.series_type}</Badge>
          </div>
          <div className="mt-1 text-xl font-semibold">{h.product}</div>
          <div className="mt-1 text-sm text-ink-2">
            {h.customer}{" "}
            <span className="text-muted">
              · {h.customer_location} · {h.region} · {h.channel} · {h.category} / {h.brand}
            </span>
          </div>
          <div className="mt-1 text-xs text-muted">{s.classification_reason}</div>
        </div>
        <Segmented<Measure>
          value={measure}
          onChange={setMeasure}
          options={[
            { value: "units", label: "Units" },
            { value: "revenue", label: "Revenue" },
          ]}
        />
      </div>
      <div className="grid grid-cols-2 divide-x divide-y divide-line md:grid-cols-3 xl:grid-cols-6 xl:divide-y-0">
        <HeaderStat
          label="Champion model"
          value={s.champion}
          sub={<ConfidenceBadge value={s.confidence} />}
        />
        <HeaderStat label="Forecast accuracy" value={pct(s.accuracy)} sub="1 − WMAPE (backtest)" />
        <HeaderStat label="WMAPE" value={pct(s.wmape)} sub={`stability σ ${pct(s.stability, 1)}`} />
        <HeaderStat label="Bias" value={pct(s.bias, 1, true)} sub={<BiasBadge value={s.bias_class} />} />
        <HeaderStat
          label={`Next month · ${n ? monthLabel(n.date) : ""}`}
          value={fmtMeasure(n?.consensus, measure)}
          sub={n && n.consensus !== n.base ? `base ${fmtMeasure(n.base, measure)}` : "consensus = base"}
        />
        <HeaderStat
          label="Confidence interval (P10–P90)"
          value={n ? `${fmtMeasure(n.p10, measure)} – ${fmtMeasure(n.p90, measure)}` : "—"}
          sub="empirical, out-of-sample"
          small
        />
      </div>
    </div>
  );
}

function HeaderStat({
  label,
  value,
  sub,
  small,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  small?: boolean;
}) {
  return (
    <div className="px-5 py-3.5">
      <div className="label-xs">{label}</div>
      <div className={clsx("mt-1 font-semibold tracking-tight", small ? "text-base" : "text-xl")}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </div>
  );
}

function ChampionCard({ d }: { d: Detail }) {
  const s = d.selection!;
  const champ = d.leaderboard?.find((r) => r.champion_flag);
  const chall = d.leaderboard?.find((r) => r.challenger_flag);
  const gap = s.challenger_wmape != null ? s.challenger_wmape - s.wmape : null;
  return (
    <Card title="Champion vs Challenger" subtitle="Selected by WMAPE, then |bias|, then RMSE">
      <div className="space-y-3">
        {[
          { role: "Champion", r: champ, color: "border-emerald-300 bg-emerald-50/60" },
          { role: "Challenger", r: chall, color: "border-slate-200 bg-slate-50" },
        ].map(({ role, r, color }) =>
          r ? (
            <div key={role} className={clsx("rounded-lg border p-3", color)}>
              <div className="flex items-center justify-between">
                <span className="label-xs">{role}</span>
                {role === "Champion" && <Trophy size={14} className="text-emerald-600" />}
              </div>
              <div className="mt-1 font-semibold">{r.model}</div>
              <div className="text-[11px] text-muted">{r.family}</div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
                <div>
                  <div className="text-muted">WMAPE</div>
                  <div className="font-semibold">{pct(r.wmape)}</div>
                </div>
                <div>
                  <div className="text-muted">Bias</div>
                  <div className="font-semibold">{pct(r.bias, 1, true)}</div>
                </div>
                <div>
                  <div className="text-muted">MASE</div>
                  <div className="font-semibold">{r.mase?.toFixed(2) ?? "—"}</div>
                </div>
              </div>
            </div>
          ) : null,
        )}
        <div className="rounded-lg border border-line p-3 text-xs">
          <div className="flex justify-between">
            <span className="text-muted">Champion margin</span>
            <span className="font-semibold">{gap != null ? `${(gap * 100).toFixed(1)} pts WMAPE` : "—"}</span>
          </div>
          <div className="mt-1 flex justify-between">
            <span className="text-muted">Confidence score</span>
            <span className="font-semibold">
              {s.confidence_score}/100 · {s.confidence}
            </span>
          </div>
          <div className="mt-1 flex justify-between">
            <span className="text-muted">History</span>
            <span className="font-semibold">{s.history_months} months</span>
          </div>
          <div className="mt-2 text-muted">Candidates routed: {s.candidates.join(", ")}</div>
        </div>
        {champ?.parameters && Object.keys(champ.parameters).length > 0 && (
          <details className="text-xs">
            <summary className="cursor-pointer text-muted">Champion parameters</summary>
            <pre className="mt-1 overflow-auto rounded bg-slate-50 p-2 text-[11px]">
              {JSON.stringify(champ.parameters, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </Card>
  );
}

function Leaderboard({ rows }: { rows: LeaderRow[] }) {
  return (
    <Card
      title="Model leaderboard (this series)"
      subtitle="Rolling-origin backtest: 4 folds × 3 months, expanding window"
    >
      <DataTable
        rows={rows}
        maxHeight={340}
        rowKey={(r) => r.model}
        columns={[
          {
            key: "rank",
            label: "Rank",
            align: "center",
            render: (r) => (r.rank ? <span className="font-semibold">{r.rank}</span> : "—"),
          },
          {
            key: "model",
            label: "Model",
            render: (r) => (
              <span className="flex items-center gap-1.5">
                {r.model}
                {r.champion_flag && <Badge className="bg-emerald-50 text-emerald-800">Champion</Badge>}
                {r.challenger_flag && <Badge className="bg-slate-100 text-slate-700">Challenger</Badge>}
              </span>
            ),
          },
          {
            key: "family",
            label: "Family",
            render: (r) => <span className="text-xs text-muted">{r.family}</span>,
          },
          { key: "wmape", label: "WMAPE", align: "right", format: "percent" },
          { key: "bias", label: "Bias", align: "right", format: "percent_signed" },
          { key: "rmse", label: "RMSE", align: "right", render: (r) => units(r.rmse) },
          { key: "mase", label: "MASE", align: "right", format: "number" },
          { key: "wmape_std", label: "Stability σ", align: "right", format: "percent" },
          {
            key: "status",
            label: "Status",
            render: (r) =>
              r.status === "ok" ? (
                <span className="text-xs text-emerald-700">ok</span>
              ) : (
                <span className="text-xs text-muted">{r.status}</span>
              ),
          },
        ]}
      />
    </Card>
  );
}

function BacktestCard({ d }: { d: Detail }) {
  const s = d.selection!;
  const bt = d.backtest ?? [];
  const dates = Array.from(new Set(bt.map((b) => b.date))).sort();
  const get = (model: string | null) =>
    dates.map((dt) => bt.find((b) => b.model === model && b.date === dt)?.forecast ?? null);
  const actual = dates.map((dt) => bt.find((b) => b.date === dt)?.actual ?? null);
  return (
    <Card
      title="Backtest: out-of-sample forecasts vs actual"
      subtitle="Each fold trains only on data before its origin (no leakage)"
    >
      <SimpleLineChart
        categories={dates.map((x) => shortMonth(x))}
        series={[
          { name: "Actual", data: actual, color: SERIES.actual },
          { name: `Champion · ${s.champion}`, data: get(s.champion), color: SERIES.base },
          ...(s.challenger
            ? [
                {
                  name: `Challenger · ${s.challenger}`,
                  data: get(s.challenger),
                  color: SERIES.challenger,
                  dashed: true,
                },
              ]
            : []),
        ]}
        format="units"
        height={320}
      />
    </Card>
  );
}

function OverridesCard({ d }: { d: Detail }) {
  const qc = useQueryClient();
  const { data: library } = useGet<{ type: string; typical_uplift: number; description: string }[]>(
    "/api/overrides/event-library",
  );
  const horizon = Array.from(new Set((d.baseline_vs_incremental ?? []).map((r) => r.date)));
  const [form, setForm] = useState({
    date: "",
    event_type: "Promotion",
    uplift: 15,
    comment: "",
    scope: "series",
  });
  useEffect(() => {
    if (!form.date && horizon.length) setForm((f) => ({ ...f, date: horizon[0] }));
  }, [horizon, form.date]);
  const create = useMutation({
    mutationFn: () =>
      api.post("/api/overrides", {
        customer: d.header.customer,
        sku: form.scope === "series" ? d.header.sku : null,
        date: form.date,
        event_type: form.event_type,
        uplift_pct: form.uplift / 100,
        comment: form.comment,
        created_by: "Demand Planner",
      }),
    onSuccess: () => {
      setForm((f) => ({ ...f, comment: "" }));
      qc.invalidateQueries();
    },
  });
  const del = useMutation({
    mutationFn: (id: string) => api.del(`/api/overrides/${id}`),
    onSuccess: () => qc.invalidateQueries(),
  });
  return (
    <Card
      title="Commercial overrides"
      subtitle="Events that move the consensus away from the statistical base"
    >
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Field label="Month">
          <select
            className="input"
            value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })}
          >
            {horizon.map((m) => (
              <option key={m} value={m}>
                {monthLabel(m)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Event">
          <select
            className="input"
            value={form.event_type}
            onChange={(e) => {
              const ev = library?.find((l) => l.type === e.target.value);
              setForm({
                ...form,
                event_type: e.target.value,
                uplift: ev ? Math.round(ev.typical_uplift * 100) : form.uplift,
              });
            }}
          >
            {(library ?? []).map((l) => (
              <option key={l.type} value={l.type}>
                {l.type}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Expected uplift %">
          <input
            className="input"
            type="number"
            value={form.uplift}
            onChange={(e) => setForm({ ...form, uplift: Number(e.target.value) })}
          />
        </Field>
        <Field label="Applies to">
          <select
            className="input"
            value={form.scope}
            onChange={(e) => setForm({ ...form, scope: e.target.value })}
          >
            <option value="series">This SKU at this customer</option>
            <option value="customer">All SKUs of {d.header.customer}</option>
          </select>
        </Field>
      </div>
      <div className="mt-3 flex gap-3">
        <input
          className="input"
          placeholder="Comment (e.g. New merchandising campaign)"
          value={form.comment}
          onChange={(e) => setForm({ ...form, comment: e.target.value })}
        />
        <button
          type="button"
          className="btn-primary shrink-0"
          onClick={() => create.mutate()}
          disabled={create.isPending || !form.date}
        >
          <Plus size={15} /> Add override
        </button>
      </div>
      <ErrorState error={create.error} />
      <ul className="mt-4 divide-y divide-slate-100">
        {(d.overrides ?? []).length === 0 && (
          <li className="py-4 text-center text-sm text-muted">No overrides for this series.</li>
        )}
        {(d.overrides ?? []).map((o) => (
          <li key={o.override_id} className="flex items-center gap-3 py-2.5">
            <Badge
              className={o.uplift_pct >= 0 ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800"}
            >
              {pct(o.uplift_pct, 0, true)}
            </Badge>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium">
                {o.event_type} · {monthLabel(o.date)}{" "}
                {o.sku ? "" : <span className="text-xs text-muted">(all SKUs of customer)</span>}
              </div>
              <div className="truncate text-xs text-muted">
                {o.comment || "—"} · {o.created_by}
              </div>
            </div>
            <button
              type="button"
              className="btn-ghost px-2 py-1"
              onClick={() => del.mutate(o.override_id)}
              aria-label="Delete override"
            >
              <Trash2 size={14} />
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

// ---------------------------------------------------------------------------- hierarchy
const LEVELS: { level: string; dim?: FilterDim; label: string }[] = [
  { level: "company", label: "Company" },
  { level: "region", dim: "region", label: "Region" },
  { level: "channel", dim: "channel", label: "Channel" },
  { level: "customer", dim: "customer", label: "Customer" },
  { level: "category", dim: "category", label: "Category" },
  { level: "sku", dim: "sku", label: "SKU" },
];

interface HierRow {
  member: string;
  actual_ltm: number;
  forecast_12m: number;
  consensus_12m: number;
  budget_12m: number;
  target_12m: number;
  gap_vs_budget: number;
  gap_vs_budget_pct: number;
  wmape: number;
  bias: number;
  growth_vs_ltm: number;
  n_series: number;
}

function HierarchyExplorer() {
  const { filters, setFilter, measure } = useFilters();
  const { data: dims } = useDimensions();
  const [level, setLevel] = useState("region");
  const [method, setMethod] = useState<"bottom_up" | "top_down">("bottom_up");
  const { data: agg } = useGet<{
    timeline: TimelineRow[];
    totals: Totals;
    metrics: { accuracy: number; wmape: number; bias: number };
    n_series: number;
    has_run: boolean;
  }>("/api/forecast/aggregate", { ...filters, measure });
  const { data: table } = useGet<{ rows: HierRow[]; next_level: string | null }>("/api/forecast/hierarchy", {
    ...filters,
    measure,
    level,
    method,
  });
  const idx = LEVELS.findIndex((l) => l.level === level);
  const productName = (sku: string) => dims?.sku.find((s) => s.sku === sku)?.product;
  const drill = (member: string) => {
    const cur = LEVELS[idx];
    if (cur.dim) setFilter(cur.dim, member);
    if (idx < LEVELS.length - 1) setLevel(LEVELS[idx + 1].level);
  };
  const fmt = (v: number) => fmtMeasure(v, measure);
  const t = agg?.totals;
  if (agg && !agg.has_run) return <NoRunState />;
  return (
    <div>
      <FilterBar />
      <div className="mb-4 flex flex-wrap items-center gap-1 text-sm">
        {LEVELS.slice(1).map((l, i) => (
          <span key={l.level} className="flex items-center gap-1">
            {i > 0 && <ChevronRight size={14} className="text-muted" />}
            <button
              type="button"
              onClick={() => setLevel(l.level)}
              className={clsx(
                "rounded-md px-2 py-1",
                level === l.level ? "bg-ink text-white" : "text-ink-2 hover:bg-slate-100",
              )}
            >
              {l.label}
              {l.dim && filters[l.dim] ? `: ${filters[l.dim]}` : ""}
            </button>
          </span>
        ))}
        <div className="ml-auto">
          <Segmented
            value={method}
            onChange={setMethod}
            size="xs"
            options={[
              { value: "bottom_up", label: "Bottom-up" },
              { value: "top_down", label: "Top-down (hist. shares)" },
            ]}
          />
        </div>
      </div>
      {t && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 2xl:grid-cols-5">
          <KpiCard
            label="Actual LTM"
            icon={<History />}
            tone="navy"
            value={fmt(t.actual_ltm)}
            delta={pct(t.actual_ltm / t.actual_prior_ltm - 1, 1, true)}
            hint="YoY"
          />
          <KpiCard
            label="Statistical 12M"
            icon={<ChartLine />}
            tone="blue"
            value={fmt(t.base ?? 0)}
            hint={`P10 ${fmt(t.p10 ?? 0)} · P90 ${fmt(t.p90 ?? 0)}`}
          />
          <KpiCard
            label="Consensus 12M"
            icon={<Users />}
            tone="green"
            value={fmt(t.consensus ?? 0)}
            delta={pct((t.consensus ?? 0) / t.actual_ltm - 1, 1, true)}
            hint="vs LTM"
          />
          <KpiCard
            label="vs Budget"
            icon={<PiggyBank />}
            tone="orange"
            value={pct((t.consensus ?? 0) / (t.budget ?? 1) - 1, 1, true)}
            deltaTone={(t.consensus ?? 0) >= (t.budget ?? 0) ? "good" : "bad"}
            hint={`Budget ${fmt(t.budget ?? 0)}`}
          />
          <KpiCard
            label="Accuracy"
            icon={<Crosshair />}
            tone="green"
            value={pct(agg?.metrics.accuracy)}
            hint={`${agg?.n_series} series · bias ${pct(agg?.metrics.bias, 1, true)}`}
          />
        </div>
      )}
      <Card
        className="mt-5"
        title="Aggregated plan (bottom-up reconciled)"
        subtitle="Every level is the exact sum of its Customer × SKU forecasts"
      >
        <TimelineChart
          rows={agg?.timeline ?? []}
          measure={measure}
          lastActual={agg ? lastActual(agg.timeline) : undefined}
          height={340}
        />
      </Card>
      <Card
        className="mt-5"
        title={`By ${LEVELS[idx]?.label.toLowerCase()}`}
        subtitle={idx < LEVELS.length - 1 ? "Click a row to drill down" : undefined}
      >
        <DataTable
          rows={table?.rows ?? []}
          rowKey={(r) => r.member}
          onRowClick={idx < LEVELS.length - 1 ? (r) => drill(r.member) : undefined}
          columns={[
            {
              key: "member",
              label: LEVELS[idx]?.label ?? "Member",
              render: (r) => (level === "sku" ? `${r.member} · ${productName(r.member) ?? ""}` : r.member),
            },
            { key: "n_series", label: "Series", align: "right", format: "number" },
            { key: "actual_ltm", label: "Actual LTM", align: "right", render: (r) => fmt(r.actual_ltm) },
            {
              key: "forecast_12m",
              label: "Statistical 12M",
              align: "right",
              render: (r) => fmt(r.forecast_12m),
            },
            {
              key: "consensus_12m",
              label: "Consensus 12M",
              align: "right",
              render: (r) => fmt(r.consensus_12m),
            },
            { key: "growth_vs_ltm", label: "Growth", align: "right", format: "percent_signed" },
            { key: "budget_12m", label: "Budget 12M", align: "right", render: (r) => fmt(r.budget_12m) },
            {
              key: "gap_vs_budget_pct",
              label: "vs Budget",
              align: "right",
              render: (r) => (
                <span className={r.gap_vs_budget_pct >= 0 ? "text-emerald-700" : "text-red-700"}>
                  {pct(r.gap_vs_budget_pct, 1, true)}
                </span>
              ),
            },
            { key: "target_12m", label: "Target 12M", align: "right", render: (r) => fmt(r.target_12m) },
            { key: "wmape", label: "WMAPE", align: "right", format: "percent" },
            { key: "bias", label: "Bias", align: "right", format: "percent_signed" },
          ]}
        />
      </Card>
    </div>
  );
}
