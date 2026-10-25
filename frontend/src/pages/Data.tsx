import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Ban,
  CheckCircle2,
  Database,
  Download,
  FileUp,
  Info,
  Microscope,
  Sparkles,
  Table2,
  TriangleAlert,
  UploadCloud,
} from "lucide-react";
import { useRef, useState } from "react";

import { BarChart, SimpleLineChart } from "../charts/BasicCharts";
import { EChart, AXIS_STYLE, TOOLTIP_STYLE } from "../charts/EChart";
import { DataTable } from "../components/DataTable";
import { FilterBar } from "../components/FilterBar";
import { Signature } from "../components/Layout";
import { Badge, Card, ErrorState, Field, KpiCard, Loader, PageHeader, Tabs } from "../components/ui";
import { useGet } from "../hooks/useApi";
import { useFilters } from "../hooks/useFilters";
import { SERIES } from "../lib/colors";
import { formatValue, full, money, pct, shortMonth, units } from "../lib/format";
import { api } from "../services/api";
import type { DatasetInfo, ValidationReport } from "../types";

type Tab = "upload" | "explore" | "profiles" | "datasets";

export default function Data() {
  const [tab, setTab] = useState<Tab>("upload");
  return (
    <div>
      <PageHeader
        eyebrow="Data"
        title="Data Hub"
        subtitle="Upload Excel / CSV / Parquet, validate it with the Dataset Health Check, explore demand and profile every series before forecasting."
        actions={
          <a className="btn-secondary" href="/api/data/template">
            <Download size={15} /> Download template
          </a>
        }
      />
      <Tabs<Tab>
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "upload", label: "Upload & Health Check", icon: <UploadCloud size={15} /> },
          { value: "explore", label: "Exploratory Analysis", icon: <Microscope size={15} /> },
          { value: "profiles", label: "Series Profiling", icon: <Sparkles size={15} /> },
          { value: "datasets", label: "Datasets & Preview", icon: <Table2 size={15} /> },
        ]}
      />
      <div className="mt-5">
        {tab === "upload" && <UploadTab />}
        {tab === "explore" && <ExploreTab />}
        {tab === "profiles" && <ProfilesTab />}
        {tab === "datasets" && <DatasetsTab />}
      </div>
    </div>
  );
}

interface UploadResult {
  file_name: string;
  accepted: boolean;
  dataset_version: string | null;
  run_id: string | null;
  run_message?: string;
  validation: ValidationReport;
  quality_label: string;
}

function UploadTab() {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const [seed, setSeed] = useState(42);
  const [result, setResult] = useState<UploadResult | null>(null);
  const { data: active } = useGet<DatasetInfo>("/api/data/active", undefined, { retry: false });
  const upload = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return api.post<UploadResult>("/api/data/upload", fd);
    },
    onSuccess: (r) => {
      setResult(r);
      if (r.accepted) qc.invalidateQueries();
    },
  });
  const demo = useMutation({
    mutationFn: () => api.post<{ dataset_version: string }>("/api/data/demo", { seed, run_forecast: true }),
    onSuccess: () => {
      setResult(null);
      qc.invalidateQueries();
    },
  });
  const report = result?.validation ?? active?.validation;
  const pick = (f?: File | null) => f && upload.mutate(f);

  return (
    <div className="grid gap-5 xl:grid-cols-[420px_1fr]">
      <div className="flex flex-col gap-5">
        <Card
          title="Upload sales history"
          subtitle="Minimum columns: Date, Region, Channel, Customer, SKU, Units"
        >
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              pick(e.dataTransfer.files?.[0]);
            }}
            onClick={() => input.current?.click()}
            className={clsx(
              "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-10 text-center transition",
              drag ? "border-brand bg-blue-50" : "border-slate-200 hover:border-brand/60 hover:bg-slate-50",
            )}
          >
            <FileUp size={28} className="text-brand" />
            <div className="text-sm font-semibold">Drop a file here or click to browse</div>
            <div className="text-xs text-muted">.xlsx · .csv · .parquet — up to 50 MB</div>
            <input
              ref={input}
              type="file"
              accept=".xlsx,.xls,.csv,.parquet"
              className="hidden"
              onChange={(e) => pick(e.target.files?.[0])}
            />
          </div>
          {upload.isPending && <Loader label="Validating file…" />}
          <ErrorState error={upload.error} />
          <div className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-ink-2">
            Optional columns: Price, Promotion, Marketing, StockOut, Distribution, Revenue, Category, Brand,
            Product, CustomerLocation, CustomerPotential. A sheet named <b>Plan</b> with BudgetUnits /
            TargetUnits is used as the budget; otherwise the budget is derived from last year.
          </div>
          <div className="mt-4 border-t border-line pt-4">
            <Signature variant="inline" />
          </div>
        </Card>
        <Card
          title="Synthetic demo dataset"
          subtitle="60 months · 14 customers · 24 SKUs · reproducible by random seed"
        >
          <div className="flex items-end gap-3">
            <Field label="random_seed">
              <input
                className="input w-28"
                type="number"
                value={seed}
                onChange={(e) => setSeed(Number(e.target.value))}
              />
            </Field>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => demo.mutate()}
              disabled={demo.isPending}
            >
              <Database size={15} /> {demo.isPending ? "Generating…" : "Load demo & run forecast"}
            </button>
          </div>
          <ErrorState error={demo.error} />
        </Card>
      </div>

      <div className="flex flex-col gap-5">
        {result && (
          <div
            className={clsx(
              "flex items-start gap-3 rounded-xl border px-4 py-3 text-sm",
              result.accepted
                ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                : "border-red-200 bg-red-50 text-red-900",
            )}
          >
            {result.accepted ? <CheckCircle2 size={18} /> : <Ban size={18} />}
            <div>
              <b>{result.file_name}</b>{" "}
              {result.accepted
                ? `accepted as ${result.dataset_version}. ${result.run_id ? `Forecast run ${result.run_id} started.` : (result.run_message ?? "")}`
                : "was not accepted."}
            </div>
          </div>
        )}
        {report ? (
          <HealthReport
            report={report}
            title={
              result
                ? `Dataset Health Check — ${result.file_name}`
                : `Dataset Health Check — ${active?.dataset_version ?? ""}`
            }
          />
        ) : (
          <Card title="Dataset Health Check">
            <div className="py-10 text-center text-sm text-muted">Upload a file to see its health check.</div>
          </Card>
        )}
      </div>
    </div>
  );
}

function QualityRing({ score }: { score: number }) {
  const r = 46;
  const c = 2 * Math.PI * r;
  const color = score >= 90 ? "#0ca30c" : score >= 75 ? "#1baf7a" : score >= 60 ? "#fab219" : "#d03b3b";
  return (
    <svg width="120" height="120" viewBox="0 0 120 120" role="img" aria-label={`Data quality score ${score}`}>
      <circle cx="60" cy="60" r={r} stroke="#eef0f3" strokeWidth="10" fill="none" />
      <circle
        cx="60"
        cy="60"
        r={r}
        stroke={color}
        strokeWidth="10"
        fill="none"
        strokeLinecap="round"
        strokeDasharray={`${(c * score) / 100} ${c}`}
        transform="rotate(-90 60 60)"
      />
      <text x="60" y="64" textAnchor="middle" fontSize="28" fontWeight="700" fill="#0b1220">
        {Math.round(score)}
      </text>
      <text x="60" y="82" textAnchor="middle" fontSize="10" fill="#64748b">
        / 100
      </text>
    </svg>
  );
}

const SEV_ICON = {
  critical: <Ban size={15} className="text-red-600" />,
  warning: <TriangleAlert size={15} className="text-amber-600" />,
  info: <Info size={15} className="text-sky-600" />,
};

export function HealthReport({ report, title }: { report: ValidationReport; title: string }) {
  const s = report.summary;
  const q = report.quality;
  const missingTotal = Object.values((s.missing_values ?? {}) as Record<string, number>).reduce(
    (a, b) => a + b,
    0,
  );
  const stats: [string, string][] = [
    ["Rows", full(s.rows)],
    ["SKUs", full(s.n_skus)],
    ["Customers", full(s.n_customers)],
    ["Series", full(s.n_series)],
    ["Start date", s.start_date?.slice(0, 7) ?? "—"],
    ["End date", s.end_date?.slice(0, 7) ?? "—"],
    ["Missing values", full(missingTotal)],
    ["Duplicated rows", full(s.duplicated_rows)],
    ["Invalid dates", full(s.invalid_dates)],
    ["Negative values", full(s.negative_values)],
    ["Zero-demand periods", full(s.zero_demand_periods)],
    ["Outliers", full(s.outliers)],
    [
      "History length",
      s.history
        ? `${s.history.min_months}–${s.history.max_months} mo (median ${s.history.median_months})`
        : "—",
    ],
    ["Short series", full(s.history?.short_series)],
  ];
  return (
    <Card title={title} subtitle={`Status: ${report.status.toUpperCase()}`}>
      {!report.can_forecast && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-300 bg-red-50 px-4 py-3 font-semibold text-red-800">
          <Ban size={18} /> Forecast execution blocked. Fix the critical issues below and upload again.
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-[auto_1fr]">
        <div className="flex flex-col items-center">
          <div className="label-xs mb-1">Data Quality Score</div>
          <QualityRing score={q.overall} />
          <div className="mt-3 w-56 space-y-2">
            {(
              [
                ["Completeness", q.completeness],
                ["Consistency", q.consistency],
                ["Historical Depth", q.historical_depth],
                ["Granularity", q.granularity],
              ] as const
            ).map(([label, v]) => (
              <div key={label}>
                <div className="flex justify-between text-xs">
                  <span className="text-ink-2">{label}</span>
                  <span className="font-semibold tabular">{v.toFixed(0)}%</span>
                </div>
                <div className="mt-0.5 h-1.5 rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-brand" style={{ width: `${v}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-4">
            {stats.map(([k, v]) => (
              <div key={k}>
                <div className="text-[11px] text-muted">{k}</div>
                <div className="text-sm font-semibold tabular">{v}</div>
              </div>
            ))}
          </div>
          <div className="mt-5">
            <div className="label-xs mb-2">Validation issues</div>
            <ul className="space-y-2">
              {report.issues.length === 0 && (
                <li className="flex items-center gap-2 text-sm text-emerald-700">
                  <CheckCircle2 size={15} /> No issues found.
                </li>
              )}
              {report.issues.map((i) => (
                <li key={i.code} className="rounded-lg border border-line px-3 py-2">
                  <div className="flex items-center gap-2 text-sm">
                    {SEV_ICON[i.severity]}
                    <span className="font-medium">{i.message}</span>
                    <Badge
                      className={clsx(
                        "ml-auto",
                        i.severity === "critical" && "bg-red-100 text-red-800",
                        i.severity === "warning" && "bg-amber-50 text-amber-800",
                        i.severity === "info" && "bg-sky-50 text-sky-800",
                      )}
                    >
                      {i.severity}
                    </Badge>
                  </div>
                  {Array.isArray(i.examples) &&
                    i.examples.length > 0 &&
                    typeof i.examples[0] === "object" && (
                      <div className="mt-1.5 overflow-x-auto text-[11px] text-muted">
                        {(i.examples as Record<string, unknown>[]).map((e, idx) => (
                          <div key={idx} className="font-mono">
                            {Object.entries(e)
                              .map(([k, v]) => `${k}=${v}`)
                              .join("  ")}
                          </div>
                        ))}
                      </div>
                    )}
                </li>
              ))}
            </ul>
          </div>
          <div className="mt-4 text-[11px] text-muted">
            Column mapping:{" "}
            {Object.entries(report.column_mapping)
              .map(([a, b]) => (a === b ? a : `${a}→${b}`))
              .join(" · ")}
          </div>
        </div>
      </div>
    </Card>
  );
}

interface Eda {
  measure: string;
  monthly: { date: string; value: number; trend: number | null }[];
  seasonality: { month: number; index: number }[];
  volatility: { date: string; cv: number }[];
  kpis: Record<string, number | null>;
  promotion: { promo_index: number; no_promo_index: number; uplift: number; promo_share: number } | null;
  merchandising: { uplift: number } | null;
  distribution: { corr: number | null; points: [number, number][] };
  breakdown: Record<string, { name: string; value: number }[]>;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function ExploreTab() {
  const { filters, measure } = useFilters();
  const { data, isLoading, error } = useGet<Eda>("/api/data/eda", { ...filters, measure });
  const fmt = measure === "revenue" ? "currency" : "units";
  return (
    <div>
      <FilterBar />
      <ErrorState error={error} />
      {isLoading && <Loader />}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-6">
            <KpiCard label="Last 12 months" value={formatValue(data.kpis.total_ltm, fmt)} />
            <KpiCard label="YoY growth" value={pct(data.kpis.yoy_growth, 1, true)} />
            <KpiCard
              label="Peak month"
              value={data.kpis.peak_month ? MONTHS[data.kpis.peak_month - 1] : "—"}
              hint={`amplitude ${pct(data.kpis.seasonal_amplitude, 0)}`}
            />
            <KpiCard label="Volatility (CV)" value={pct(data.kpis.volatility_cv)} hint="rolling 12M, total" />
            <KpiCard
              label="Promo uplift"
              value={pct(data.promotion?.uplift, 0, true)}
              hint={`${pct(data.promotion?.promo_share, 0)} of months on promo`}
            />
            <KpiCard
              label="Zero-demand share"
              value={pct(data.kpis.zero_demand_share)}
              hint="intermittency"
            />
          </div>
          <div className="mt-5 grid gap-5 xl:grid-cols-[1.6fr_1fr]">
            <Card
              title="Historical demand & trend"
              subtitle="Monthly total with 2×12 centred moving-average trend"
            >
              <SimpleLineChart
                categories={data.monthly.map((m) => shortMonth(m.date))}
                series={[
                  { name: "Demand", data: data.monthly.map((m) => m.value), color: SERIES.actual },
                  { name: "Trend", data: data.monthly.map((m) => m.trend), color: SERIES.base, dashed: true },
                ]}
                format={fmt}
                height={320}
              />
            </Card>
            <Card
              title="Seasonality index"
              subtitle="Average demand / trend by calendar month (1.0 = average)"
            >
              <BarChart
                categories={data.seasonality.map((s) => MONTHS[s.month - 1])}
                series={[{ name: "Index", data: data.seasonality.map((s) => s.index), color: SERIES.base }]}
                format="number"
                height={320}
              />
            </Card>
          </div>
          <div className="mt-5 grid gap-5 xl:grid-cols-3">
            <Card title="Volatility" subtitle="Rolling 12-month coefficient of variation">
              <SimpleLineChart
                categories={data.volatility.map((v) => shortMonth(v.date))}
                series={[{ name: "CV", data: data.volatility.map((v) => v.cv), color: SERIES.budget }]}
                format="percent"
                height={260}
              />
            </Card>
            <Card
              title="Distribution vs demand"
              subtitle={`Each dot = series-month; demand relative to series median · corr ${data.distribution.corr?.toFixed(2) ?? "—"}`}
            >
              <EChart
                height={260}
                option={{
                  grid: { left: 48, right: 16, top: 16, bottom: 36 },
                  tooltip: {
                    ...TOOLTIP_STYLE,
                    formatter: (p: { value: number[] }) =>
                      `Distribution ${p.value[0]}%<br/>Demand index ${p.value[1].toFixed(2)}`,
                  },
                  xAxis: {
                    type: "value",
                    name: "Numeric distribution %",
                    nameLocation: "middle",
                    nameGap: 24,
                    min: 0,
                    max: 100,
                    ...AXIS_STYLE,
                  },
                  yAxis: { type: "value", ...AXIS_STYLE, axisLine: { show: false } },
                  series: [
                    {
                      type: "scatter",
                      symbolSize: 6,
                      data: data.distribution.points,
                      itemStyle: { color: SERIES.base, opacity: 0.55 },
                    },
                  ],
                }}
              />
            </Card>
            <Card title="Promotion & merchandising effect" subtitle="Demand index vs each series' own median">
              {data.promotion ? (
                <BarChart
                  categories={["No promotion", "Promotion"]}
                  series={[
                    {
                      name: "Demand index",
                      data: [data.promotion.no_promo_index, data.promotion.promo_index],
                      color: SERIES.consensus,
                    },
                  ]}
                  format="number"
                  height={220}
                />
              ) : (
                <div className="py-10 text-center text-sm text-muted">
                  No promotion column in this dataset.
                </div>
              )}
              {data.merchandising && (
                <div className="text-xs text-muted">
                  Merchandising uplift: {pct(data.merchandising.uplift, 0, true)}
                </div>
              )}
            </Card>
          </div>
          <div className="mt-5 grid gap-5 xl:grid-cols-3">
            {(["category", "channel", "region"] as const).map((d) => (
              <Card key={d} title={`Last 12 months by ${d}`}>
                <BarChart
                  categories={(data.breakdown[d] ?? []).map((b) => b.name)}
                  series={[
                    {
                      name: measure,
                      data: (data.breakdown[d] ?? []).map((b) => b.value),
                      color: SERIES.base,
                    },
                  ]}
                  horizontal
                  format={fmt}
                  height={220}
                />
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

interface Profiles {
  types: { type: string; count: number }[];
  intermittency: { class: string; count: number }[];
  rows: Record<string, any>[];
}

function ProfilesTab() {
  const { filters } = useFilters();
  const { data, isLoading } = useGet<Profiles>("/api/data/profiles", filters);
  return (
    <div>
      <FilterBar showMeasure={false} />
      {isLoading && <Loader />}
      {data && (
        <>
          <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
            <Card
              title="Series Type Classification"
              subtitle="Rule-based on ADI/CV², STL trend & seasonal strength, change-points and driver correlation"
            >
              <BarChart
                categories={data.types.map((t) => t.type)}
                series={[{ name: "Series", data: data.types.map((t) => t.count), color: SERIES.base }]}
                horizontal
                format="number"
                height={300}
              />
            </Card>
            <Card
              title="Intermittency (Syntetos–Boylan)"
              subtitle="ADI ≥ 1.32 → intermittent; CV² ≥ 0.49 → erratic / lumpy"
            >
              <BarChart
                categories={data.intermittency.map((t) => t.class)}
                series={[
                  { name: "Series", data: data.intermittency.map((t) => t.count), color: SERIES.consensus },
                ]}
                format="number"
                height={300}
              />
            </Card>
          </div>
          <Card
            className="mt-5"
            title="Series profiles"
            subtitle="Mean, median, variance, CV, zero-demand %, trend / seasonal strength, intermittency"
          >
            <DataTable
              rows={data.rows}
              searchable
              searchKeys={["customer", "sku", "product", "series_type"]}
              initialSort={{ key: "mean", dir: "desc" }}
              rowKey={(r) => r.series_id}
              columns={[
                { key: "customer", label: "Customer" },
                { key: "sku", label: "SKU" },
                { key: "product", label: "Product" },
                {
                  key: "series_type",
                  label: "Type",
                  render: (r) => <Badge className="bg-blue-50 text-blue-800">{r.series_type}</Badge>,
                },
                {
                  key: "classification_reason",
                  label: "Why",
                  render: (r) => <span className="wrap text-xs text-muted">{r.classification_reason}</span>,
                },
                { key: "n_obs", label: "Months", align: "right", format: "number" },
                { key: "mean", label: "Mean", align: "right", render: (r) => units(r.mean) },
                { key: "median", label: "Median", align: "right", render: (r) => units(r.median) },
                { key: "cv", label: "CV", align: "right", format: "percent" },
                { key: "zero_pct", label: "Zero %", align: "right", format: "percent" },
                { key: "adi", label: "ADI", align: "right", format: "number" },
                { key: "trend_strength", label: "Trend str.", align: "right", format: "number" },
                { key: "seasonal_strength", label: "Season str.", align: "right", format: "number" },
                { key: "promo_lift", label: "Promo lift", align: "right", format: "percent_signed" },
                { key: "intermittency", label: "Demand class" },
              ]}
            />
          </Card>
        </>
      )}
    </div>
  );
}

function DatasetsTab() {
  const qc = useQueryClient();
  const { filters } = useFilters();
  const { data: list } = useGet<DatasetInfo[]>("/api/data/datasets");
  const { data: preview } = useGet<{ total: number; rows: Record<string, any>[] }>("/api/data/preview", {
    ...filters,
    limit: 300,
  });
  const activate = useMutation({
    mutationFn: (v: string) => api.post(`/api/data/datasets/${v}/activate`),
    onSuccess: () => qc.invalidateQueries(),
  });
  return (
    <div className="flex flex-col gap-5">
      <Card
        title="Dataset versions"
        subtitle="Every upload creates an immutable DatasetVersion (dataset_YYYY_MM_vNN)"
      >
        <DataTable
          rows={list ?? []}
          rowKey={(r) => r.dataset_version}
          columns={[
            {
              key: "dataset_version",
              label: "Version",
              render: (r) => <span className="font-mono text-xs">{r.dataset_version}</span>,
            },
            { key: "name", label: "Name" },
            { key: "source", label: "Source" },
            {
              key: "created_at",
              label: "Created",
              render: (r) => String(r.created_at).slice(0, 16).replace("T", " "),
            },
            { key: "n_rows", label: "Rows", align: "right", format: "number" },
            { key: "n_series", label: "Series", align: "right", format: "number" },
            {
              key: "start_date",
              label: "Period",
              render: (r) => `${String(r.start_date).slice(0, 7)} → ${String(r.end_date).slice(0, 7)}`,
            },
            { key: "quality_score", label: "Quality", align: "right", format: "number" },
            {
              key: "plan_source",
              label: "Plan",
              render: (r) => <span className="wrap text-xs text-muted">{r.plan_source}</span>,
            },
            {
              key: "is_active",
              label: "",
              render: (r) =>
                r.is_active ? (
                  <Badge className="bg-emerald-50 text-emerald-800">Active</Badge>
                ) : (
                  <button
                    type="button"
                    className="btn-secondary px-2 py-1 text-xs"
                    onClick={() => activate.mutate(r.dataset_version)}
                  >
                    Activate
                  </button>
                ),
            },
          ]}
        />
      </Card>
      <FilterBar showMeasure={false} />
      <Card title="Dataset preview" subtitle={`${full(preview?.total)} rows · most recent first`}>
        <DataTable
          rows={preview?.rows ?? []}
          maxHeight={520}
          dense
          columns={[
            { key: "date", label: "Date", render: (r) => String(r.date).slice(0, 7) },
            { key: "region", label: "Region" },
            { key: "channel", label: "Channel" },
            { key: "customer", label: "Customer" },
            { key: "sku", label: "SKU" },
            { key: "product", label: "Product" },
            { key: "units", label: "Units", align: "right", format: "number" },
            { key: "revenue", label: "Revenue", align: "right", render: (r) => money(r.revenue) },
            { key: "price", label: "Price", align: "right", format: "number" },
            { key: "promotion", label: "Promo", align: "right", format: "number" },
            { key: "distribution", label: "Dist. %", align: "right", format: "number" },
            { key: "stockout", label: "Stock-out", align: "right", format: "number" },
            {
              key: "marketing_investment",
              label: "Marketing",
              align: "right",
              render: (r) => money(r.marketing_investment),
            },
            { key: "merchandising_event", label: "Merch", align: "right", format: "number" },
          ]}
        />
      </Card>
    </div>
  );
}
