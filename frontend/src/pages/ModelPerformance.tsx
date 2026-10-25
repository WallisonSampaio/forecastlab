import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BarChart3, Boxes, Grid3x3, History, ListOrdered } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { BarChart, Heatmap } from "../charts/BasicCharts";
import { DataTable } from "../components/DataTable";
import { FilterBar } from "../components/FilterBar";
import { NoRunState, RunForecastButton } from "../components/RunControls";
import {
  Badge,
  BiasBadge,
  Card,
  ConfidenceBadge,
  KpiCard,
  Loader,
  PageHeader,
  Segmented,
  Tabs,
} from "../components/ui";
import { useGet } from "../hooks/useApi";
import { useFilters } from "../hooks/useFilters";
import { SERIES } from "../lib/colors";
import { pct } from "../lib/format";
import { api } from "../services/api";
import type { Job, LeaderRow } from "../types";

type Tab = "leaderboard" | "heatmaps" | "series" | "registry";

export default function ModelPerformance() {
  const [tab, setTab] = useState<Tab>("leaderboard");
  return (
    <div>
      <PageHeader
        eyebrow="Model governance"
        title="Model Performance Center"
        subtitle="Leaderboard, champion distribution, accuracy & bias heatmaps, stability and the model / run registries."
        actions={<RunForecastButton />}
      />
      <FilterBar showMeasure={false} />
      <Tabs<Tab>
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "leaderboard", label: "Leaderboard", icon: <ListOrdered size={15} /> },
          { value: "heatmaps", label: "Accuracy & bias heatmaps", icon: <Grid3x3 size={15} /> },
          { value: "series", label: "Champion vs challenger by series", icon: <Boxes size={15} /> },
          { value: "registry", label: "Model & run registry", icon: <History size={15} /> },
        ]}
      />
      <div className="mt-5">
        {tab === "leaderboard" && <LeaderboardTab />}
        {tab === "heatmaps" && <HeatmapsTab />}
        {tab === "series" && <SeriesTab />}
        {tab === "registry" && <RegistryTab />}
      </div>
    </div>
  );
}

interface Distribution {
  by_model: { model: string; count: number }[];
  by_family: { family: string; count: number }[];
  by_type: { series_type: string; champion: string; count: number }[];
  confidence: { level: string; count: number }[];
}

function LeaderboardTab() {
  const { filters } = useFilters();
  const { data: lb, isLoading } = useGet<LeaderRow[]>("/api/models/leaderboard", filters);
  const { data: dist } = useGet<Distribution>("/api/models/distribution", filters);
  const pivot = useMemo(() => {
    if (!dist) return { types: [] as string[], models: [] as string[], cell: new Map<string, number>() };
    const types = Array.from(new Set(dist.by_type.map((r) => r.series_type)));
    const models = dist.by_model.map((m) => m.model);
    const cell = new Map(dist.by_type.map((r) => [`${r.series_type}|${r.champion}`, r.count]));
    return { types, models, cell };
  }, [dist]);
  if (isLoading) return <Loader />;
  if (!lb?.length) return <NoRunState />;
  const total = dist?.by_model.reduce((a, b) => a + b.count, 0) ?? 0;
  const high = dist?.confidence.find((c) => c.level === "High")?.count ?? 0;
  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <KpiCard
          label="Models competing"
          value={lb.length}
          hint="routed per demand pattern"
          icon={<BarChart3 size={16} />}
        />
        <KpiCard label="Series" value={total} hint="Customer × SKU" />
        <KpiCard label="Best pooled WMAPE" value={pct(lb[0].wmape)} hint={lb[0].model} />
        <KpiCard label="High confidence" value={pct(total ? high / total : 0, 0)} hint={`${high} series`} />
      </div>
      <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
        <Card
          title="Model leaderboard"
          subtitle="Pooled out-of-sample WMAPE over the series where each model competed"
        >
          <DataTable
            rows={lb}
            rowKey={(r) => r.model}
            maxHeight={520}
            columns={[
              {
                key: "rank",
                label: "Rank",
                align: "center",
                render: (r) => <span className="font-semibold">{r.rank}</span>,
              },
              { key: "model", label: "Model", render: (r) => <span className="font-medium">{r.model}</span> },
              {
                key: "family",
                label: "Family",
                render: (r) => <span className="text-xs text-muted">{r.family}</span>,
              },
              { key: "wmape", label: "WMAPE", align: "right", format: "percent" },
              { key: "bias", label: "Bias", align: "right", format: "percent_signed" },
              { key: "bias_class", label: "", render: (r) => <BiasBadge value={r.bias_class} /> },
              { key: "rmse", label: "RMSE", align: "right", format: "number" },
              { key: "series_evaluated", label: "Series", align: "right", format: "number" },
              { key: "champion_count", label: "Champion", align: "right", format: "number" },
              { key: "challenger_count", label: "Challenger", align: "right", format: "number" },
              { key: "win_rate", label: "Win rate", align: "right", format: "percent" },
            ]}
          />
        </Card>
        <Card title="Champion distribution" subtitle="How often each model wins">
          <BarChart
            categories={(dist?.by_model ?? []).map((m) => m.model)}
            series={[
              { name: "Series", data: (dist?.by_model ?? []).map((m) => m.count), color: SERIES.base },
            ]}
            horizontal
            format="number"
            height={480}
          />
        </Card>
      </div>
      <Card
        title="Champion model by demand pattern"
        subtitle="Rows = series type, columns = champion model (count of series)"
      >
        <div className="overflow-auto">
          <table className="table-base tabular">
            <thead>
              <tr>
                <th>Series type</th>
                {pivot.models.map((m) => (
                  <th key={m} className="text-right">
                    {m}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pivot.types.map((t) => (
                <tr key={t}>
                  <td className="font-medium">{t}</td>
                  {pivot.models.map((m) => {
                    const v = pivot.cell.get(`${t}|${m}`) ?? 0;
                    return (
                      <td
                        key={m}
                        className="text-right"
                        style={{
                          background: v ? `rgba(42,120,214,${Math.min(0.55, 0.08 + v / 25)})` : undefined,
                        }}
                      >
                        {v || ""}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

interface HeatmapData {
  metric: string;
  customers: string[];
  skus: string[];
  cells: {
    customer: string;
    sku: string;
    product: string;
    value: number | null;
    class: string | null;
    champion: string;
    series_id: string;
  }[];
}

function HeatmapsTab() {
  const { filters } = useFilters();
  const [metric, setMetric] = useState<"wmape" | "bias">("wmape");
  const nav = useNavigate();
  const { data, isLoading } = useGet<HeatmapData>("/api/models/heatmap", { ...filters, metric });
  if (isLoading) return <Loader />;
  if (!data?.cells.length) return <NoRunState />;
  return (
    <Card
      title={
        metric === "wmape"
          ? "Forecast Accuracy Heatmap — WMAPE by Customer × SKU"
          : "Forecast Bias Heatmap — Customer × SKU"
      }
      subtitle={
        metric === "wmape"
          ? "Darker = higher error. Click a cell to open the series in the workspace."
          : "Blue = under-forecast · gray = balanced · red = over-forecast. Click a cell to open the series."
      }
      actions={
        <Segmented
          value={metric}
          onChange={setMetric}
          options={[
            { value: "wmape", label: "WMAPE" },
            { value: "bias", label: "Bias" },
          ]}
        />
      }
    >
      <Heatmap
        rows={data.customers}
        cols={data.skus}
        cells={data.cells.map((c) => ({ row: c.customer, col: c.sku, value: c.value }))}
        mode={metric === "wmape" ? "sequential" : "diverging"}
        max={metric === "wmape" ? 0.6 : 0.3}
        format={metric === "wmape" ? "percent" : "percent_signed"}
        height={Math.max(420, data.customers.length * 34 + 90)}
        onClick={(row, col) => {
          const cell = data.cells.find((c) => c.customer === row && c.sku === col);
          if (cell) nav(`/app/forecasting?mode=series&series=${encodeURIComponent(cell.series_id)}`);
        }}
      />
    </Card>
  );
}

interface PerfRow {
  series_id: string;
  customer: string;
  sku: string;
  product: string;
  series_type: string;
  champion: string;
  wmape: number;
  accuracy: number;
  bias: number;
  bias_class: string;
  challenger: string;
  challenger_wmape: number;
  gap_vs_challenger: number;
  wmape_std: number;
  confidence: string;
  confidence_score: number;
  history_months: number;
}

function SeriesTab() {
  const { filters } = useFilters();
  const nav = useNavigate();
  const { data, isLoading } = useGet<PerfRow[]>("/api/models/performance", filters);
  if (isLoading) return <Loader />;
  return (
    <Card
      title="Champion & challenger by series"
      subtitle="Stability = std-dev of WMAPE across backtest folds · click a row to open the workspace"
    >
      <DataTable
        rows={data ?? []}
        searchable
        searchKeys={["customer", "sku", "product", "champion", "series_type"]}
        rowKey={(r) => r.series_id}
        onRowClick={(r) => nav(`/app/forecasting?mode=series&series=${encodeURIComponent(r.series_id)}`)}
        maxHeight={640}
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
            key: "champion",
            label: "Champion",
            render: (r) => <span className="font-medium">{r.champion}</span>,
          },
          { key: "wmape", label: "WMAPE", align: "right", format: "percent" },
          { key: "bias", label: "Bias", align: "right", format: "percent_signed" },
          { key: "challenger", label: "Challenger" },
          { key: "challenger_wmape", label: "Chall. WMAPE", align: "right", format: "percent" },
          { key: "gap_vs_challenger", label: "Margin", align: "right", format: "percent" },
          { key: "wmape_std", label: "Stability σ", align: "right", format: "percent" },
          { key: "confidence", label: "Confidence", render: (r) => <ConfidenceBadge value={r.confidence} /> },
        ]}
      />
    </Card>
  );
}

function RegistryTab() {
  const qc = useQueryClient();
  const { data: runs } = useGet<Job[]>("/api/forecast/runs");
  const { data: reg } = useGet<Record<string, any>[]>("/api/models/registry", { limit: 800 });
  const activate = useMutation({
    mutationFn: (id: string) => api.post(`/api/forecast/runs/${id}/activate`),
    onSuccess: () => qc.invalidateQueries(),
  });
  return (
    <div className="flex flex-col gap-5">
      <Card
        title="Forecast Run Registry"
        subtitle="RunID · timestamp · dataset version · horizon · engine version · scenario · status · duration"
      >
        <DataTable
          rows={runs ?? []}
          rowKey={(r) => r.run_id}
          columns={[
            {
              key: "run_id",
              label: "Run ID",
              render: (r) => <span className="font-mono text-xs">{r.run_id}</span>,
            },
            {
              key: "created_at",
              label: "Timestamp",
              render: (r) => String(r.created_at).slice(0, 19).replace("T", " "),
            },
            {
              key: "dataset_version",
              label: "Dataset",
              render: (r) => <span className="font-mono text-xs">{r.dataset_version}</span>,
            },
            { key: "horizon", label: "Horizon", align: "right", render: (r) => `${r.horizon} m` },
            { key: "model_version", label: "Engine" },
            { key: "scenario", label: "Scenario" },
            { key: "n_series", label: "Series", align: "right", format: "number" },
            { key: "n_models", label: "Models", align: "right", format: "number" },
            {
              key: "duration_s",
              label: "Duration",
              align: "right",
              render: (r) => (r.duration_s ? `${Math.round(r.duration_s)} s` : "—"),
            },
            {
              key: "summary",
              label: "WMAPE",
              align: "right",
              render: (r) => pct((r.summary as { wmape?: number } | undefined)?.wmape),
            },
            {
              key: "status",
              label: "Status",
              render: (r) => (
                <Badge
                  className={
                    r.status === "completed"
                      ? "bg-emerald-50 text-emerald-800"
                      : r.status === "failed"
                        ? "bg-red-50 text-red-800"
                        : "bg-blue-50 text-blue-800"
                  }
                >
                  {r.status}
                </Badge>
              ),
            },
            {
              key: "act",
              label: "",
              render: (r) =>
                r.status === "completed" ? (
                  <button
                    type="button"
                    className="btn-secondary px-2 py-1 text-xs"
                    onClick={() => activate.mutate(r.run_id)}
                  >
                    Use run
                  </button>
                ) : null,
            },
          ]}
        />
      </Card>
      <Card
        title="Model Registry"
        subtitle="SeriesID · Model · ModelVersion · TrainingDate · WMAPE · Bias · Parameters · ChampionFlag (first 800 rows)"
      >
        <DataTable
          rows={reg ?? []}
          searchable
          searchKeys={["series_id", "model"]}
          maxHeight={560}
          dense
          columns={[
            {
              key: "series_id",
              label: "Series ID",
              render: (r) => <span className="text-xs">{r.series_id}</span>,
            },
            { key: "model", label: "Model" },
            {
              key: "model_version",
              label: "Version",
              render: (r) => <span className="font-mono text-xs">{r.model_version}</span>,
            },
            {
              key: "training_date",
              label: "Training date",
              render: (r) => String(r.training_date).slice(0, 10),
            },
            { key: "status", label: "Status" },
            { key: "wmape", label: "WMAPE", align: "right", format: "percent" },
            { key: "bias", label: "Bias", align: "right", format: "percent_signed" },
            { key: "rank", label: "Rank", align: "right", format: "number" },
            {
              key: "parameters",
              label: "Parameters",
              render: (r) => (
                <span className="font-mono text-[11px] text-muted">
                  {JSON.stringify(r.parameters).slice(0, 80)}
                </span>
              ),
            },
            {
              key: "champion_flag",
              label: "Champion",
              render: (r) =>
                r.champion_flag ? <Badge className="bg-emerald-50 text-emerald-800">✓</Badge> : "",
            },
          ]}
        />
      </Card>
    </div>
  );
}
