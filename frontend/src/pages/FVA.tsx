/**
 * Forecast Value Added: do the commercial adjustments improve the forecast?
 * The `/app/fva` route redirects to `/app/models?tab=fva`; the content is rendered there through the
 * exported `FvaContent` (spec §3). The default export stays as a standalone page.
 */
import clsx from "clsx";
import {
  ArrowRight,
  ChartColumnDecreasing,
  ClipboardList,
  Gauge,
  ScrollText,
  Sigma,
  Sparkles,
  ThumbsUp,
  Users,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { BarChart } from "../charts/BasicCharts";
import { DataTable } from "../components/DataTable";
import { FilterBar } from "../components/FilterBar";
import { NoRunState } from "../components/RunControls";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  KpiCard,
  Loader,
  PageHeader,
  Segmented,
} from "../components/ui";
import { useGet } from "../hooks/useApi";
import { useFilters } from "../hooks/useFilters";
import { STATUS, TONES } from "../lib/colors";
import { full, monthLabel, pct, pp } from "../lib/format";
import { groupLabel, t } from "../lib/labels";

interface Group {
  overrides: number;
  improved_pct: number;
  wmape_statistical: number | null;
  wmape_consensus: number | null;
  fva_pp: number | null;
  fva_units: number;
  avg_adjustment: number;
  [k: string]: unknown;
}

interface OverrideRow {
  date: string;
  customer: string;
  sku: string;
  product?: string;
  planner: string;
  event_type: string;
  comment?: string | null;
  adjustment_pct: number;
  statistical: number;
  consensus: number;
  actual: number;
  error_statistical?: number;
  error_consensus?: number;
  fva_units: number;
  outcome: string;
  direction?: string;
}

export interface FvaData {
  available: boolean;
  message?: string;
  stairstep: {
    naive: number | null;
    statistical: number | null;
    consensus: number | null;
    fva_statistical_vs_naive: number | null;
    fva_consensus_vs_statistical: number | null;
  };
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
  overrides: OverrideRow[];
}

type GroupKey = "planner" | "event_type" | "direction" | "magnitude";

/* ------------------------------------------------------------------ helpers */

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** WMAPE points with an explicit sign: 0.012 -> "+1,2 p.p." */
const ppSigned = (v: number | null | undefined) => pp(v, 1, true);

const signedUnits = (v: number | null | undefined) => (isNum(v) ? `${v > 0 ? "+" : ""}${full(v)}` : "—");

/** Magnitude buckets come from the API as "< 10%", "10-20%", "> 20%" (|ajuste|). */
const MAGNITUDE: Record<string, string> = {
  "< 10%": "Até 10%",
  "10-20%": "De 10% a 20%",
  "> 20%": "Acima de 20%",
};

const groupName = (dim: GroupKey, value: unknown) =>
  dim === "magnitude" ? (MAGNITUDE[String(value)] ?? String(value)) : groupLabel(dim, String(value));

const OUTCOME_STYLE: Record<string, string> = {
  Improved: "bg-emerald-50 text-emerald-800",
  Worsened: "bg-red-50 text-red-800",
  Neutral: "bg-slate-100 text-slate-700",
};

function FvaValue({ v, children }: { v: number | null | undefined; children: ReactNode }) {
  return (
    <span
      className={clsx(
        "font-semibold",
        !isNum(v) || v === 0 ? "text-ink-2" : v > 0 ? "text-emerald-700" : "text-red-700",
      )}
    >
      {children}
    </span>
  );
}

/**
 * Inline diverging bar for the group table: the track is centred on zero, value added grows to the
 * right (green), value destroyed to the left (red). The signed value is always written next to it.
 */
function FvaBar({ v, max }: { v: number | null | undefined; max: number }) {
  const share = isNum(v) && max > 0 ? Math.min(1, Math.abs(v) / max) : 0;
  return (
    <span className="inline-flex items-center justify-end gap-2.5">
      <span aria-hidden className="relative block h-2.5 w-[120px] shrink-0 rounded-full bg-[#eef1fa]">
        <span className="absolute inset-y-[-3px] left-1/2 w-px bg-[#c3c8d9]" />
        {isNum(v) && v !== 0 && (
          <span
            className="absolute inset-y-0 rounded-full"
            style={{
              width: `${share * 50}%`,
              left: v > 0 ? "50%" : `${50 - share * 50}%`,
              background: v > 0 ? STATUS.good : STATUS.critical,
            }}
          />
        )}
      </span>
      <span className="min-w-[78px] text-right">
        <FvaValue v={v}>{ppSigned(v)}</FvaValue>
      </span>
    </span>
  );
}

function StepChip({ label, value, className }: { label: string; value: number | null; className: string }) {
  return (
    <div className={clsx("min-w-[96px] rounded-2xl px-4 py-2 text-center", className)}>
      <div className="text-[11px] font-semibold uppercase tracking-wider opacity-80">{label}</div>
      <div className="text-base font-bold">{pct(value)}</div>
    </div>
  );
}

function StepGain({ value }: { value: number | null }) {
  return (
    <div className="flex flex-col items-center gap-0.5 px-1">
      <ArrowRight size={15} className="text-muted" />
      <FvaValue v={value}>
        <span className="whitespace-nowrap text-[11px]">{ppSigned(value)}</span>
      </FvaValue>
    </div>
  );
}

/** Below half a tenth of a point the stairstep step reads as "no change". */
const PP_EPS = 0.0005;

/**
 * One sentence reading the stairstep ("o estatístico erra 12,5 p.p. a menos que o ingênuo…").
 * Without historical adjustments the consensus equals the statistical forecast: say so instead of
 * reporting a "+0,0 p.p." gain.
 */
function stairstepReading(st: FvaData["stairstep"], hasOverrides: boolean): string | null {
  const a = st.fva_statistical_vs_naive;
  const b = st.fva_consensus_vs_statistical;
  if (!isNum(a)) return null;
  const abs = (v: number) => pp(Math.abs(v));
  const first =
    a >= 0
      ? `O modelo estatístico erra ${abs(a)} a menos que o método ingênuo`
      : `O modelo estatístico erra ${abs(a)} a mais que o método ingênuo`;
  const second = !hasOverrides
    ? "sem histórico de ajustes comerciais, o consenso é igual ao estatístico."
    : !isNum(b) || Math.abs(b) < PP_EPS
      ? "os ajustes comerciais praticamente não mudam o erro."
      : b > 0
        ? `os ajustes comerciais reduzem o erro em mais ${abs(b)}` // "p.p." already ends the sentence
        : `os ajustes comerciais aumentam o erro em ${abs(b)}`;
  return `${first}; ${second}`;
}

/* --------------------------------------------------------------------- page */

export default function FVA() {
  return (
    <div>
      <PageHeader
        eyebrow="Valor agregado ao forecast"
        icon={<Sparkles />}
        title="Os ajustes humanos melhoram o forecast?"
        subtitle="Ingênuo → Estatístico (campeão, fora da amostra) → Consenso (após os ajustes comerciais dos planejadores), comparados célula a célula (Cliente × SKU × Mês) nos últimos 12 meses."
      />
      <FilterBar showMeasure={false} />
      <FvaContent />
    </div>
  );
}

/**
 * The FVA analysis for the current filters (`useFilters`): KPIs, stairstep, value added by group and
 * the adjustment log. Rendered as the "Valor dos ajustes (FVA)" tab of `/app/models`.
 */
export function FvaContent() {
  const { filters } = useFilters();
  const { data, isLoading, error } = useGet<FvaData>("/api/fva", filters);
  if (isLoading) return <Loader />;
  if (error && !data) return <ErrorState error={error} />;
  if (!data?.available) return <NoRunState />;
  const filtered = Object.values(filters).some((v) => v != null && v !== "");
  return <FvaBody data={data} filtered={filtered} />;
}

function FvaBody({ data, filtered }: { data: FvaData; filtered: boolean }) {
  const s = data.summary;
  const st = data.stairstep;
  const fvaOv = s.fva_pp_overridden;
  const fvaStat = st.fva_statistical_vs_naive;
  const hasOverrides = (s.overrides ?? 0) > 0;
  const reading = stairstepReading(st, hasOverrides);
  const noOverridesHint = filtered
    ? "nenhum ajuste histórico neste recorte"
    : "sem ajustes históricos na base";

  return (
    <div data-testid="fva-content">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Ajustes que agregaram valor"
          icon={<ThumbsUp />}
          tone="green"
          value={pct(s.value_added_pct, 0)}
          hint={
            hasOverrides
              ? `${full(s.improved ?? 0)} melhoraram · ${full(s.worsened ?? 0)} pioraram · ${full(s.neutral ?? 0)} neutros`
              : noOverridesHint
          }
        />
        <KpiCard
          label="FVA dos ajustes"
          icon={<Gauge />}
          tone="blue"
          value={ppSigned(fvaOv)}
          delta={isNum(fvaOv) ? (fvaOv >= 0 ? "agregou valor" : "destruiu valor") : undefined}
          deltaTone={isNum(fvaOv) && fvaOv >= 0 ? "good" : "bad"}
          hint={
            hasOverrides
              ? `WMAPE nas células ajustadas: ${pct(s.wmape_statistical_overridden)} → ${pct(s.wmape_consensus_overridden)}`
              : noOverridesHint
          }
        />
        <KpiCard
          label="FVA do estatístico vs ingênuo"
          icon={<Sigma />}
          tone="navy"
          value={ppSigned(fvaStat)}
          delta={isNum(fvaStat) ? (fvaStat >= 0 ? "modelo supera o ingênuo" : "ingênuo é melhor") : undefined}
          deltaTone={isNum(fvaStat) && fvaStat >= 0 ? "good" : "bad"}
          hint={`Ingênuo ${pct(st.naive)} → Estatístico ${pct(st.statistical)}`}
        />
        <KpiCard
          label="Ajustes avaliados"
          icon={<ClipboardList />}
          tone="yellow"
          value={full(s.overrides)}
          hint={`${full(data.cells_evaluated)} células avaliadas · ${full(data.pending_overrides)} ajustes futuros em aberto`}
        />
      </div>

      <Card
        className="mt-5"
        title="Escada do FVA"
        subtitle="WMAPE em cada etapa do processo (quanto menor, melhor)"
        icon={<ChartColumnDecreasing />}
        tone="blue"
      >
        <div className="grid items-center gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
          <BarChart
            categories={["Ingênuo", "Estatístico", "Consenso"]}
            series={[{ name: "WMAPE", data: [st.naive, st.statistical, st.consensus] }]}
            format="percent"
            height={240}
            highlight={2}
          />
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center justify-center gap-2">
              <StepChip label="Ingênuo" value={st.naive} className="bg-slate-100 text-slate-700" />
              <StepGain value={st.fva_statistical_vs_naive} />
              <StepChip label="Estatístico" value={st.statistical} className={TONES.blue.soft} />
              <StepGain value={st.fva_consensus_vs_statistical} />
              <StepChip label="Consenso" value={st.consensus} className={TONES.green.soft} />
            </div>
            {reading && <p className="text-sm leading-relaxed text-ink-2">{reading}</p>}
          </div>
        </div>
      </Card>

      {hasOverrides ? <OverrideAnalysis data={data} /> : <NoOverrides filtered={filtered} />}
    </div>
  );
}

/** No historical adjustments (base or filters): nothing to group or log; the stairstep above still holds. */
function NoOverrides({ filtered }: { filtered: boolean }) {
  return (
    <div className="card mt-5">
      <EmptyState
        title={filtered ? "Sem ajustes comerciais neste recorte" : "Sem histórico de ajustes comerciais"}
        icon={<ScrollText />}
      >
        {filtered
          ? "Nenhum ajuste comercial histórico para os filtros selecionados. Limpe os filtros para ver o valor agregado da base toda."
          : "Sem histórico de ajustes comerciais para medir o valor agregado. A escada acima compara apenas o método ingênuo com o modelo estatístico."}
      </EmptyState>
    </div>
  );
}

/** Value added by group (inline diverging bars) and the adjustment log. */
function OverrideAnalysis({ data }: { data: FvaData }) {
  const [group, setGroup] = useState<GroupKey>("event_type");
  const groups: Record<GroupKey, Group[]> = {
    planner: data.by_planner,
    event_type: data.by_event_type,
    direction: data.by_direction,
    magnitude: data.by_magnitude,
  };
  const rows = groups[group] ?? [];
  const maxFva = Math.max(0, ...rows.map((r) => (isNum(r.fva_pp) ? Math.abs(r.fva_pp) : 0)));
  const logRows = useMemo(
    () =>
      (data.overrides ?? []).map((r) => ({
        ...r,
        planner_label: t.planner(r.planner),
        event_label: t.event(r.event_type),
        outcome_label: t.outcome(r.outcome),
      })),
    [data.overrides],
  );
  return (
    <>
      <Card
        className="mt-5"
        title="Valor agregado por grupo"
        subtitle="FVA = WMAPE(estatístico) − WMAPE(consenso) nas células ajustadas, em pontos de WMAPE (p.p.) · à direita do zero o ajuste melhorou o forecast"
        icon={<Users />}
        tone="teal"
        actions={
          <Segmented<GroupKey>
            size="xs"
            value={group}
            onChange={setGroup}
            options={[
              { value: "event_type", label: "Tipo de evento" },
              { value: "planner", label: "Planejador" },
              { value: "direction", label: "Direção" },
              { value: "magnitude", label: "Magnitude" },
            ]}
          />
        }
      >
        {rows.length === 0 ? (
          <EmptyState title="Sem ajustes neste recorte">
            Não há ajustes comerciais históricos para os filtros selecionados.
          </EmptyState>
        ) : (
          <DataTable
            rows={rows}
            rowKey={(r) => String(r[group])}
            maxHeight={420}
            initialSort={{ key: "fva_pp", dir: "desc" }}
            columns={[
              {
                key: group,
                label: t.dimension(group),
                sortValue: (r) => groupName(group, r[group]),
                render: (r) => <span className="font-semibold text-ink">{groupName(group, r[group])}</span>,
              },
              {
                key: "fva_pp",
                label: "FVA",
                align: "right",
                render: (r) => <FvaBar v={r.fva_pp} max={maxFva} />,
              },
              { key: "overrides", label: "Ajustes", align: "right", format: "number" },
              { key: "improved_pct", label: "% que melhorou", align: "right", format: "percent" },
              { key: "avg_adjustment", label: "Ajuste médio", align: "right", format: "percent_signed" },
              { key: "wmape_statistical", label: "WMAPE estatístico", align: "right", format: "percent" },
              { key: "wmape_consensus", label: "WMAPE consenso", align: "right", format: "percent" },
            ]}
          />
        )}
      </Card>

      <Card
        className="mt-5"
        title="Log de ajustes"
        subtitle="Todos os ajustes comerciais históricos com o resultado, do que mais destruiu valor ao que mais agregou"
        icon={<ScrollText />}
        tone="navy"
      >
        <DataTable
          rows={logRows}
          searchable
          searchKeys={[
            "customer",
            "sku",
            "planner_label",
            "event_label",
            "outcome_label",
            "comment",
            "planner",
            "event_type",
          ]}
          maxHeight={520}
          dense
          empty="Nenhum ajuste histórico para os filtros selecionados"
          columns={[
            {
              key: "date",
              label: "Mês",
              render: (r) => monthLabel(r.date),
            },
            { key: "customer", label: "Cliente" },
            { key: "sku", label: "SKU" },
            {
              key: "planner_label",
              label: "Planejador",
              render: (r) => <span className="text-ink-2">{r.planner_label}</span>,
            },
            {
              key: "event_label",
              label: "Evento",
              render: (r) => <Badge className={TONES.purple.soft}>{r.event_label}</Badge>,
            },
            {
              key: "comment",
              label: "Comentário",
              render: (r) => <span className="wrap text-xs text-muted">{r.comment || "—"}</span>,
            },
            { key: "adjustment_pct", label: "Ajuste", align: "right", format: "percent_signed" },
            { key: "statistical", label: "Estatístico", align: "right", render: (r) => full(r.statistical) },
            { key: "consensus", label: "Com ajuste", align: "right", render: (r) => full(r.consensus) },
            { key: "actual", label: "Real", align: "right", render: (r) => full(r.actual) },
            {
              key: "fva_units",
              label: "FVA (unid.)",
              align: "right",
              render: (r) => <FvaValue v={r.fva_units}>{signedUnits(r.fva_units)}</FvaValue>,
            },
            {
              key: "outcome_label",
              label: "Resultado",
              render: (r) => (
                <Badge className={OUTCOME_STYLE[r.outcome] ?? "bg-slate-100 text-slate-700"}>
                  {r.outcome_label}
                </Badge>
              ),
            },
          ]}
        />
      </Card>
    </>
  );
}
