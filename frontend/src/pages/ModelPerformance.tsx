/**
 * "Modelos e FVA" (governance): who won the model competition, by how much, whether the commercial
 * adjustments helped (FVA) and the run / model registries. Tabs live in the URL (`?tab=`, spec §3).
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { BarChart3, Check, Database, History, LayoutGrid, ListOrdered, Sparkles, Swords } from "lucide-react";
import { useMemo } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { DataTable } from "../components/DataTable";
import { FilterBar } from "../components/FilterBar";
import { NoRunState, RunForecastButton } from "../components/RunControls";
import {
  Badge,
  Card,
  ConfidenceBadge,
  ErrorState,
  Loader,
  PageHeader,
  ProgressBar,
  Tabs,
} from "../components/ui";
import { useGet } from "../hooks/useApi";
import { useFilters } from "../hooks/useFilters";
import { TONES } from "../lib/colors";
import { full, pct, pp } from "../lib/format";
import { t } from "../lib/labels";
import { ROUTES, type ModelsTab } from "../lib/routes";
import { api } from "../services/api";
import type { DatasetInfo, Job, LeaderRow } from "../types";
import { FvaContent } from "./FVA";

const TABS: ModelsTab[] = ["ranking", "series", "fva", "registro"];
const parseTab = (v: string | null): ModelsTab =>
  TABS.includes(v as ModelsTab) ? (v as ModelsTab) : "ranking";

interface Distribution {
  by_model: { model: string; count: number }[];
  by_family: { family: string; count: number }[];
  by_type: { series_type: string; champion: string; count: number }[];
  confidence: { level: string; count: number }[];
}

/* ------------------------------------------------------------------ helpers */

/** "2026-10-25T14:03:11" -> "25/10/2026 14:03" (no timezone shifts). */
function fmtDateTime(iso: unknown, withTime = true): string {
  if (!iso) return "—";
  const [date, time = ""] = String(iso).replace("T", " ").split(" ");
  const [y, m, d] = date.split("-");
  if (!y || !m || !d) return String(iso);
  return `${d.slice(0, 2)}/${m}/${y}${withTime && time ? ` ${time.slice(0, 5)}` : ""}`;
}

/** "forecastlab-engine 1.0.0" -> "v1.0.0" (full identifier stays in the tooltip). */
function engineVersion(v?: string | null): string {
  if (!v) return "—";
  const m = v.match(/\d+(?:\.\d+)+/);
  return m ? `v${m[0]}` : v;
}

const seriesName = (id: string) => id.replace("|", " · ");

function fmtDuration(s?: number | null): string {
  if (!s) return "—";
  const r = Math.round(s);
  return r < 60 ? `${r} s` : `${Math.floor(r / 60)} min ${String(r % 60).padStart(2, "0")} s`;
}

const RUN_STATUS_STYLE: Record<string, string> = {
  completed: "bg-emerald-50 text-emerald-800",
  failed: "bg-red-50 text-red-800",
  running: "bg-blue-50 text-blue-800",
  queued: "bg-amber-50 text-amber-800",
};

const REGISTRY_STATUS: Record<string, { label: string; className: string }> = {
  ok: { label: "OK", className: "bg-emerald-50 text-emerald-800" },
  no_backtest: { label: "Sem backtest", className: "bg-slate-100 text-slate-700" },
  insufficient_history: { label: "Histórico insuficiente", className: "bg-amber-50 text-amber-800" },
  failed: { label: "Falhou", className: "bg-red-50 text-red-800" },
};

/* --------------------------------------------------------------------- page */

export default function ModelPerformance() {
  const [params, setParams] = useSearchParams();
  const tab = parseTab(params.get("tab"));
  const setTab = (v: ModelsTab) =>
    setParams(
      (p) => {
        const next = new URLSearchParams(p);
        next.set("tab", v);
        return next;
      },
      { replace: true },
    );
  return (
    <div>
      <PageHeader
        eyebrow="Governança"
        icon={<BarChart3 />}
        title="Modelos e FVA"
        subtitle="Quem venceu a competição de modelos em cada série, com que margem, se os ajustes comerciais melhoraram o forecast e o registro de cada execução."
        actions={<RunForecastButton />}
      />
      <Tabs<ModelsTab>
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "ranking", label: "Ranking", icon: <ListOrdered size={15} /> },
          { value: "series", label: "Séries", icon: <Swords size={15} /> },
          { value: "fva", label: "Valor dos ajustes (FVA)", icon: <Sparkles size={15} /> },
          { value: "registro", label: "Registro", icon: <History size={15} /> },
        ]}
      />
      <div className="mt-5">
        {tab !== "registro" && <FilterBar showMeasure={false} />}
        {tab === "ranking" && <RankingTab />}
        {tab === "series" && <SeriesTab />}
        {tab === "fva" && <FvaContent />}
        {tab === "registro" && <RegistryTab />}
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- ranking */

function RankingTab() {
  const { filters } = useFilters();
  const { data: lb, isLoading, error } = useGet<LeaderRow[]>("/api/models/leaderboard", filters);
  const { data: dist } = useGet<Distribution>("/api/models/distribution", filters);
  const pivot = useMemo(() => {
    if (!dist) return { types: [] as string[], models: [] as string[], cell: new Map<string, number>() };
    const types = Array.from(new Set(dist.by_type.map((r) => r.series_type)));
    const models = dist.by_model.map((m) => m.model);
    const cell = new Map(dist.by_type.map((r) => [`${r.series_type}|${r.champion}`, r.count]));
    return { types, models, cell };
  }, [dist]);
  if (isLoading) return <Loader />;
  if (error && !lb) return <ErrorState error={error} />;
  if (!lb?.length) return <NoRunState />;
  const maxCell = Math.max(1, ...Array.from(pivot.cell.values()));
  const maxWins = Math.max(1, ...lb.map((r) => r.champion_count ?? 0));
  return (
    <div className="flex flex-col gap-5">
      <Card
        title="Ranking de modelos"
        subtitle="WMAPE de cada modelo medido apenas nas séries em que competiu — compare modelos dentro do mesmo padrão de demanda."
        icon={<ListOrdered />}
        tone="blue"
      >
        <DataTable
          rows={lb}
          rowKey={(r) => r.model}
          maxHeight={560}
          initialSort={{ key: "champion_count", dir: "desc" }}
          columns={[
            {
              key: "model",
              label: "Modelo",
              sortValue: (r) => t.model(r.model),
              render: (r) => <span className="font-semibold text-ink">{t.model(r.model)}</span>,
            },
            {
              key: "family",
              label: "Família",
              sortValue: (r) => t.family(r.family),
              render: (r) => <span className="text-xs text-muted">{t.family(r.family)}</span>,
            },
            {
              key: "champion_count",
              label: "Campeão em",
              align: "right",
              render: (r) => (
                <div className="flex items-center justify-end gap-2">
                  <div className="w-16">
                    <ProgressBar value={(r.champion_count ?? 0) / maxWins} />
                  </div>
                  <span className="min-w-[72px] whitespace-nowrap text-right font-semibold text-ink">
                    {full(r.champion_count ?? 0)} {r.champion_count === 1 ? "série" : "séries"}
                  </span>
                </div>
              ),
            },
            { key: "challenger_count", label: "Desafiante em", align: "right", format: "number" },
            { key: "series_evaluated", label: "Competiu em", align: "right", format: "number" },
            { key: "win_rate", label: "Taxa de vitória", align: "right", format: "percent" },
            { key: "wmape", label: "WMAPE", align: "right", format: "percent" },
            {
              key: "bias",
              label: "Viés",
              align: "right",
              render: (r) => (
                <span className="block leading-snug">
                  {pct(r.bias, 1, true)}
                  <span className="block text-[11px] text-muted">{t.bias(r.bias_class).toLowerCase()}</span>
                </span>
              ),
            },
          ]}
        />
      </Card>
      <Card
        title="Modelo campeão por padrão de demanda"
        subtitle="Linhas = padrão de demanda da série · colunas = modelo campeão (número de séries) · cada padrão tem o seu modelo"
        icon={<LayoutGrid />}
        tone="purple"
      >
        <div className="overflow-auto rounded-2xl border border-line bg-white/70">
          <table className="table-base tabular">
            <thead>
              <tr>
                <th>Padrão de demanda</th>
                {pivot.models.map((m) => (
                  <th key={m} className="min-w-[84px] !whitespace-normal !text-center">
                    {t.model(m)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pivot.types.map((type) => (
                <tr key={type}>
                  <td className="font-semibold text-ink">{t.seriesType(type)}</td>
                  {pivot.models.map((m) => {
                    const v = pivot.cell.get(`${type}|${m}`) ?? 0;
                    const alpha = 0.12 + (v / maxCell) * 0.78;
                    return (
                      <td key={m} className="text-center">
                        {v ? (
                          <span
                            className="inline-flex min-w-9 items-center justify-center rounded-xl px-2 py-1 text-xs font-bold"
                            style={{
                              background: `rgba(52,131,250,${alpha.toFixed(2)})`,
                              color: alpha > 0.5 ? "#ffffff" : "#2364d2",
                            }}
                          >
                            {v}
                          </span>
                        ) : (
                          <>
                            <span aria-hidden className="text-[#c9cfe2]">
                              ·
                            </span>
                            <span className="sr-only">nenhuma série</span>
                          </>
                        )}
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

/* ------------------------------------------------- champion vs challenger */

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
  const { data, isLoading, error } = useGet<PerfRow[]>("/api/models/performance", filters);
  const rows = useMemo(
    () =>
      (data ?? []).map((r) => ({
        ...r,
        type_label: t.seriesType(r.series_type),
        champion_label: t.model(r.champion),
        challenger_label: t.model(r.challenger),
      })),
    [data],
  );
  if (isLoading) return <Loader />;
  if (error && !data) return <ErrorState error={error} />;
  if (!rows.length) return <NoRunState />;
  return (
    <Card
      title="Campeão vs desafiante por série"
      subtitle="Margem = WMAPE do desafiante − WMAPE do campeão · estabilidade = desvio-padrão do WMAPE entre as janelas de backtest · clique em uma linha para abrir a série no workspace"
      icon={<Swords />}
      tone="purple"
    >
      <DataTable
        rows={rows}
        searchable
        searchKeys={[
          "customer",
          "sku",
          "product",
          "champion_label",
          "challenger_label",
          "type_label",
          "champion",
          "challenger",
        ]}
        rowKey={(r) => r.series_id}
        onRowClick={(r) => nav(ROUTES.workspace(r.series_id))}
        maxHeight={640}
        columns={[
          { key: "customer", label: "Cliente" },
          {
            key: "sku",
            label: "SKU",
            // A real link too, so the workspace is reachable from the keyboard (rows are mouse-only).
            render: (r) => (
              <Link
                to={ROUTES.workspace(r.series_id)}
                onClick={(e) => e.stopPropagation()}
                className="font-medium text-brand hover:underline"
                aria-label={`Abrir ${r.customer} · ${r.sku} no workspace de forecast`}
              >
                {r.sku}
              </Link>
            ),
          },
          {
            key: "product",
            label: "Produto",
            render: (r) => <span className="text-ink-2">{r.product}</span>,
          },
          {
            key: "type_label",
            label: "Padrão de demanda",
            render: (r) => <Badge className={TONES.blue.soft}>{r.type_label}</Badge>,
          },
          {
            key: "champion_label",
            label: "Campeão",
            render: (r) => <span className="font-semibold text-ink">{r.champion_label}</span>,
          },
          { key: "wmape", label: "WMAPE", align: "right", format: "percent" },
          { key: "bias", label: "Viés", align: "right", format: "percent_signed" },
          {
            key: "challenger_label",
            label: "Desafiante",
            render: (r) => <span className="text-ink-2">{r.challenger_label}</span>,
          },
          { key: "challenger_wmape", label: "WMAPE desafiante", align: "right", format: "percent" },
          {
            key: "gap_vs_challenger",
            label: "Margem",
            align: "right",
            render: (r) => pp(r.gap_vs_challenger),
          },
          { key: "wmape_std", label: "Estabilidade σ", align: "right", format: "percent" },
          {
            key: "confidence",
            label: "Confiança",
            sortValue: (r) => r.confidence_score,
            render: (r) => <ConfidenceBadge value={r.confidence} />,
          },
        ]}
      />
    </Card>
  );
}

/* ---------------------------------------------------------------- registry */

interface RegistryRow {
  series_id: string;
  model: string;
  model_version?: string;
  training_date?: string;
  status?: string;
  wmape?: number | null;
  bias?: number | null;
  rank?: number | null;
  parameters?: Record<string, unknown> | null;
  champion_flag?: boolean;
  challenger_flag?: boolean;
}

/** Parameters as a disclosure: the full JSON is one click away, never cut. */
function ParamsCell({ params }: { params?: Record<string, unknown> | null }) {
  const keys = params ? Object.keys(params) : [];
  if (!params || keys.length === 0) return <span className="text-muted">—</span>;
  return (
    <details className="max-w-[360px] text-[11px]">
      <summary className="cursor-pointer whitespace-nowrap font-medium text-ink-2 marker:text-muted">
        {keys.length} {keys.length === 1 ? "parâmetro" : "parâmetros"}
      </summary>
      <pre className="mt-1 whitespace-pre-wrap break-all rounded-lg bg-[#f4f6fd] p-2 font-mono text-[11px] text-ink-2">
        {JSON.stringify(params, null, 1)}
      </pre>
    </details>
  );
}

function RegistryTab() {
  const qc = useQueryClient();
  const { data: runs, isLoading } = useGet<Job[]>("/api/forecast/runs");
  const { data: reg } = useGet<RegistryRow[]>("/api/models/registry", { limit: 800 });
  const { data: ds } = useGet<DatasetInfo>("/api/data/active", undefined, {
    retry: false,
    staleTime: 30_000,
  });
  const activate = useMutation({
    mutationFn: (id: string) => api.post(`/api/forecast/runs/${id}/activate`),
    onSuccess: () => qc.invalidateQueries(),
  });
  const regRows = useMemo(
    () =>
      (reg ?? []).map((r) => ({
        ...r,
        model_label: t.model(r.model),
        status_label: REGISTRY_STATUS[r.status ?? ""]?.label ?? r.status ?? "—",
      })),
    [reg],
  );
  if (isLoading) return <Loader />;
  const activeRun = ds?.active_run;
  return (
    <div className="flex flex-col gap-5">
      <Card
        title="Registro de execuções"
        subtitle="ID da execução · data/hora · versão da base · horizonte · versão do motor · cenário · status · duração"
        icon={<History />}
        tone="navy"
      >
        {activate.error && (
          <div className="mb-3">
            <ErrorState error={activate.error} />
          </div>
        )}
        <DataTable
          rows={runs ?? []}
          rowKey={(r) => r.run_id}
          activeKey={activeRun ?? undefined}
          empty="Nenhuma execução registrada ainda"
          columns={[
            {
              key: "run_id",
              label: "ID",
              render: (r) => <span className="font-mono text-xs text-ink">{r.run_id}</span>,
            },
            {
              key: "created_at",
              label: "Data/hora",
              render: (r) => fmtDateTime(r.created_at),
            },
            {
              key: "dataset_version",
              label: "Base",
              render: (r) => <span className="font-mono text-xs">{r.dataset_version}</span>,
            },
            {
              key: "horizon",
              label: "Horizonte",
              align: "right",
              render: (r) => `${r.horizon} ${r.horizon === 1 ? "mês" : "meses"}`,
            },
            {
              key: "model_version",
              label: "Motor",
              render: (r) => (
                <span className="font-mono text-xs" title={r.model_version || undefined}>
                  {engineVersion(r.model_version)}
                </span>
              ),
            },
            {
              key: "scenario",
              label: "Cenário",
              render: (r) => t.scenarioKind(r.scenario),
            },
            { key: "n_series", label: "Séries", align: "right", format: "number" },
            { key: "n_models", label: "Modelos", align: "right", format: "number" },
            {
              key: "duration_s",
              label: "Duração",
              align: "right",
              render: (r) => fmtDuration(r.duration_s),
            },
            {
              key: "summary",
              label: "WMAPE",
              align: "right",
              sortValue: (r) => (r.summary as { wmape?: number } | undefined)?.wmape,
              render: (r) => pct((r.summary as { wmape?: number } | undefined)?.wmape),
            },
            {
              key: "status",
              label: "Status",
              render: (r) => (
                <Badge className={RUN_STATUS_STYLE[r.status] ?? "bg-slate-100 text-slate-700"}>
                  <span
                    className={clsx(
                      "h-1.5 w-1.5 rounded-full bg-current",
                      (r.status === "running" || r.status === "queued") && "animate-pulse",
                    )}
                  />
                  {t.runStatus(r.status)}
                </Badge>
              ),
            },
            {
              key: "act",
              label: "",
              render: (r) =>
                r.run_id === activeRun ? (
                  <Badge className={TONES.blue.soft}>
                    <Check size={12} strokeWidth={3} /> Em uso
                  </Badge>
                ) : r.status === "completed" ? (
                  <button
                    type="button"
                    className="btn-secondary px-3 py-1.5 text-xs"
                    disabled={activate.isPending}
                    onClick={() => activate.mutate(r.run_id)}
                  >
                    Usar execução
                  </button>
                ) : null,
            },
          ]}
        />
      </Card>
      <Card
        title="Registro de modelos"
        subtitle="Série · modelo · versão · data de treino · WMAPE · viés · parâmetros · indicador de campeão (primeiras 800 linhas)"
        icon={<Database />}
        tone="teal"
      >
        <DataTable
          rows={regRows}
          searchable
          searchKeys={["series_id", "model", "model_label", "status_label"]}
          maxHeight={560}
          dense
          columns={[
            {
              key: "series_id",
              label: "Série",
              render: (r) => <span className="text-xs text-ink">{seriesName(r.series_id)}</span>,
            },
            {
              key: "model_label",
              label: "Modelo",
              render: (r) => <span className="font-medium">{r.model_label}</span>,
            },
            {
              key: "model_version",
              label: "Versão",
              render: (r) => <span className="font-mono text-xs">{r.model_version ?? "—"}</span>,
            },
            {
              key: "training_date",
              label: "Data de treino",
              render: (r) => fmtDateTime(r.training_date, false),
            },
            {
              key: "status_label",
              label: "Status",
              render: (r) => (
                <Badge
                  className={REGISTRY_STATUS[r.status ?? ""]?.className ?? "bg-slate-100 text-slate-700"}
                >
                  {r.status_label}
                </Badge>
              ),
            },
            { key: "wmape", label: "WMAPE", align: "right", format: "percent" },
            { key: "bias", label: "Viés", align: "right", format: "percent_signed" },
            { key: "rank", label: "Posição", align: "right", format: "number" },
            {
              key: "parameters",
              label: "Parâmetros",
              sortValue: (r) => JSON.stringify(r.parameters ?? {}),
              render: (r) => <ParamsCell params={r.parameters} />,
            },
            {
              key: "champion_flag",
              label: "Campeão",
              align: "center",
              sortValue: (r) => (r.champion_flag ? 1 : 0),
              render: (r) =>
                r.champion_flag ? (
                  <Badge className="bg-emerald-50 text-emerald-800">
                    <Check size={12} strokeWidth={3} /> Sim
                  </Badge>
                ) : (
                  ""
                ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
