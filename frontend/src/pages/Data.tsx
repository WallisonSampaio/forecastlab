/**
 * "Bases de dados" (governance): dataset versions + preview, and the diagnosis of the active base.
 * Uploading and the demo base live in the Entrada stage (spec §3); this page only links there.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, Database, History, ShieldCheck, Table2, Upload } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { HealthReport, planLabel, plural, ptError, scoreColor, STATUS_TONE } from "../components/data/health";
import { DataTable } from "../components/DataTable";
import { FilterBar } from "../components/FilterBar";
import { Badge, Card, EmptyState, ErrorState, Loader, PageHeader, Tabs } from "../components/ui";
import { useGet } from "../hooks/useApi";
import { useFilters } from "../hooks/useFilters";
import { TONES } from "../lib/colors";
import { full, money, monthLabel } from "../lib/format";
import { t } from "../lib/labels";
import { ROUTES, type DataTab } from "../lib/routes";
import { api, ApiError } from "../services/api";
import type { DatasetInfo } from "../types";

/* ------------------------------------------------------------------ helpers */

const SOURCE_PT: Record<string, string> = {
  upload: "Arquivo carregado",
  synthetic_generator: "Gerador sintético",
  demo: "Demonstração",
};
function datasetName(n: string | null | undefined): string {
  if (!n) return "—";
  if (n === "upload") return "Arquivo carregado";
  const m = /^Synthetic demo dataset \(seed (\d+)\)$/i.exec(n);
  return m ? `Base sintética de demonstração (seed ${m[1]})` : n;
}
function dateTime(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return d
    .toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
    .replace(",", "");
}

const parseTab = (v: string | null): DataTab => (v === "diagnostico" ? "diagnostico" : "versoes");

/* --------------------------------------------------------------------- page */

export default function Data() {
  const [params, setParams] = useSearchParams();
  const tab = parseTab(params.get("tab"));
  const setTab = (v: DataTab) =>
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
        icon={<Database />}
        title="Bases de dados"
        subtitle="Versões carregadas, prévia das linhas e o diagnóstico de qualidade da base ativa. Para trocar de base, use a Entrada: a competição de modelos recomeça a partir dela."
        actions={
          <Link className="btn-primary" to={ROUTES.entrada({ acao: "carregar" })}>
            <Upload size={16} /> Carregar nova base
          </Link>
        }
      />
      <Tabs<DataTab>
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "versoes", label: "Versões e prévia", icon: <Table2 size={16} /> },
          { value: "diagnostico", label: "Diagnóstico", icon: <ShieldCheck size={16} /> },
        ]}
      />
      <div className="mt-6">{tab === "diagnostico" ? <DiagnosisTab /> : <DatasetsTab />}</div>
    </div>
  );
}

/* --------------------------------------------------------------- diagnosis */

function DiagnosisTab() {
  const {
    data: active,
    isLoading,
    error,
  } = useGet<DatasetInfo>("/api/data/active", undefined, {
    retry: false,
  });
  if (isLoading) return <Loader />;
  const noBase = (error instanceof ApiError && error.status === 404) || (!error && !active);
  if (noBase)
    return (
      <div className="card">
        <EmptyState title="Nenhuma base ativa" icon={<Database />}>
          Carregue uma planilha ou a base de demonstração na Entrada para ver o diagnóstico de qualidade.
          <div className="mt-4">
            <Link className="btn-primary" to={ROUTES.entrada({ acao: "carregar" })}>
              <Upload size={16} /> Ir para a Entrada
            </Link>
          </div>
        </EmptyState>
      </div>
    );
  if (error || !active) return <ErrorState error={ptError(error)} />;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs leading-relaxed text-muted">
        Base ativa <span className="font-mono text-ink-2">{active.dataset_version}</span> ·{" "}
        {full(active.n_series)} séries Cliente × SKU · {monthLabel(active.start_date)}–
        {monthLabel(active.end_date)} · orçamento e meta: {planLabel(active.plan_source)}
      </p>
      {active.validation ? (
        <HealthReport
          report={active.validation}
          title={`Diagnóstico da base ativa: ${active.dataset_version}`}
        />
      ) : (
        <div className="card">
          <EmptyState title="Diagnóstico indisponível" icon={<ShieldCheck />}>
            Esta versão da base não guardou o relatório de validação. Recarregue a planilha na Entrada para
            gerar um diagnóstico novo.
          </EmptyState>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------ datasets & preview */

interface PreviewRow {
  date: string;
  region?: string | null;
  channel?: string | null;
  customer: string;
  sku: string;
  product?: string | null;
  units?: number | null;
  revenue?: number | null;
  price?: number | null;
  marketing_investment?: number | null;
  [key: string]: unknown;
}

function DatasetsTab() {
  const qc = useQueryClient();
  const { filters } = useFilters();
  const { data: list, isLoading, error: listError } = useGet<DatasetInfo[]>("/api/data/datasets");
  const {
    data: preview,
    isLoading: previewLoading,
    error: previewError,
  } = useGet<{ total: number; rows: PreviewRow[] }>("/api/data/preview", {
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
        title="Versões da base"
        subtitle="Cada carga cria uma versão imutável (dataset_AAAA_MM_vNN); ativar uma versão antiga não apaga as outras"
        icon={<History />}
        tone="navy"
        actions={
          list ? (
            <Badge className={TONES.navy.soft}>
              {list.length} {plural(list.length, "versão", "versões")}
            </Badge>
          ) : undefined
        }
      >
        {listError && (
          <div className="mb-3">
            <ErrorState error={ptError(listError)} />
          </div>
        )}
        {isLoading ? (
          <Loader />
        ) : (
          <DataTable
            rows={list ?? []}
            rowKey={(r) => r.dataset_version}
            empty="Nenhuma base carregada ainda"
            columns={[
              {
                key: "dataset_version",
                label: "Versão",
                render: (r) => <span className="font-mono text-xs">{r.dataset_version}</span>,
              },
              { key: "name", label: "Nome", render: (r) => datasetName(r.name) },
              { key: "source", label: "Origem", render: (r) => SOURCE_PT[r.source] ?? r.source },
              { key: "created_at", label: "Criada em", render: (r) => dateTime(r.created_at) },
              { key: "n_rows", label: "Linhas", align: "right", format: "number" },
              { key: "n_series", label: "Séries", align: "right", format: "number" },
              {
                key: "start_date",
                label: "Período",
                render: (r) => `${monthLabel(r.start_date)} → ${monthLabel(r.end_date)}`,
              },
              {
                key: "quality_score",
                label: "Qualidade",
                align: "right",
                render: (r) =>
                  r.quality_score == null ? (
                    "—"
                  ) : (
                    <span className="inline-flex items-center gap-1.5 font-semibold">
                      <span
                        aria-hidden
                        className="h-2 w-2 rounded-full"
                        style={{ background: scoreColor(r.quality_score) }}
                      />
                      {full(r.quality_score, 0)}
                    </span>
                  ),
              },
              {
                key: "status",
                label: "Status",
                render: (r) => (
                  <Badge className={TONES[STATUS_TONE[r.status] ?? "blue"].soft}>
                    {t.datasetStatus(r.status)}
                  </Badge>
                ),
              },
              {
                key: "plan_source",
                label: "Plano",
                render: (r) => <span className="wrap text-xs text-muted">{planLabel(r.plan_source)}</span>,
              },
              {
                key: "is_active",
                label: "Ativa",
                sortValue: (r) => (r.is_active ? 1 : 0),
                render: (r) =>
                  r.is_active ? (
                    <Badge className={TONES.green.soft}>
                      <CircleCheck size={12} /> Ativa
                    </Badge>
                  ) : (
                    <button
                      type="button"
                      className="btn-secondary px-3 py-1 text-xs"
                      onClick={() => activate.mutate(r.dataset_version)}
                      disabled={activate.isPending || r.status === "blocked"}
                      title={r.status === "blocked" ? "Base bloqueada por erros críticos" : undefined}
                    >
                      Ativar
                    </button>
                  ),
              },
            ]}
          />
        )}
        {activate.error && (
          <div className="mt-3">
            <ErrorState error={ptError(activate.error)} />
          </div>
        )}
      </Card>

      <div>
        <FilterBar showMeasure={false} />
        <Card
          title="Prévia da base ativa"
          subtitle={
            preview
              ? `${full(preview.total)} ${plural(preview.total, "linha", "linhas")} · mais recentes primeiro`
              : "Linhas mais recentes primeiro"
          }
          icon={<Table2 />}
          tone="blue"
        >
          {previewError && (
            <div className="mb-3">
              <ErrorState error={ptError(previewError)} />
            </div>
          )}
          {previewLoading ? (
            <Loader />
          ) : (
            <DataTable
              rows={preview?.rows ?? []}
              maxHeight={520}
              dense
              empty="Nenhuma linha para os filtros selecionados"
              columns={[
                { key: "date", label: "Mês", render: (r) => monthLabel(r.date) },
                { key: "region", label: "Região" },
                { key: "channel", label: "Canal" },
                { key: "customer", label: "Cliente" },
                { key: "sku", label: "SKU" },
                { key: "product", label: "Produto" },
                { key: "units", label: "Unidades", align: "right", format: "number" },
                { key: "revenue", label: "Receita", align: "right", render: (r) => money(r.revenue) },
                { key: "price", label: "Preço", align: "right", format: "number" },
                { key: "promotion", label: "Promoção", align: "right", format: "number" },
                { key: "distribution", label: "Distrib. %", align: "right", format: "number" },
                { key: "stockout", label: "Ruptura", align: "right", format: "number" },
                {
                  key: "marketing_investment",
                  label: "Marketing",
                  align: "right",
                  render: (r) => money(r.marketing_investment),
                },
                { key: "merchandising_event", label: "Merchandising", align: "right", format: "number" },
              ]}
            />
          )}
        </Card>
      </div>
    </div>
  );
}
