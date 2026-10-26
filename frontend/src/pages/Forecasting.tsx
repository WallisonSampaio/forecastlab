/**
 * "Workspace de forecast" (tool): one Cliente × SKU series at a time — forecast, commercial
 * adjustments, champion vs challenger, backtest and the model ranking. The hierarchy explorer moved
 * to the deviation deep dive (`?mode=hierarchy` redirects there, spec §1.3 / §3).
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  BadgePercent,
  Building2,
  ChartArea,
  ChartLine,
  Crosshair,
  History,
  LineChart,
  ListOrdered,
  ListTree,
  Map as MapIcon,
  MapPin,
  Package,
  Scale,
  ScanSearch,
  Search,
  SearchX,
  Store,
  Swords,
  Tag,
  Trash2,
  TrendingDown,
  TrendingUp,
  Trophy,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Navigate, useSearchParams } from "react-router-dom";

import { SimpleLineChart } from "../charts/BasicCharts";
import { TimelineChart } from "../charts/TimelineChart";
import { DataTable } from "../components/DataTable";
import { FilterBar } from "../components/FilterBar";
import { OverrideForm, type OverrideFormDefaults } from "../components/OverrideForm";
import { NoRunState, RunForecastButton } from "../components/RunControls";
import {
  Badge,
  BiasBadge,
  Card,
  ConfidenceBadge,
  EmptyState,
  ErrorState,
  IconTile,
  Loader,
  PageHeader,
  ProgressBar,
  Segmented,
} from "../components/ui";
import { useGet } from "../hooks/useApi";
import { useFilters } from "../hooks/useFilters";
import { SERIES, STATUS, TONES, type Tone } from "../lib/colors";
import { deviationsHref } from "../lib/deviationsUrl";
import { fmtMeasure, monthLabel, pct, shortMonth, units, type Measure } from "../lib/format";
import { t } from "../lib/labels";
import { api } from "../services/api";
import type { LeaderRow, Override, SeriesRow, TimelineRow, Totals } from "../types";

/** Keeps a formatted value on one line (wraps only between values). */
const nb = (s: string) => s.replace(/ /g, " ");
const dec1 = (v: number) => v.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/** URL keys of the adjustment prefill (`ROUTES.workspace(series, {mes, evento, uplift, comentario})`). */
const PREFILL_KEYS = ["ajuste", "mes", "evento", "uplift", "comentario"] as const;

/** `?ajuste=1&mes=2026-12-01&evento=Promoção&uplift=0.2&comentario=…` -> OverrideForm defaults. */
function overridePrefill(params: URLSearchParams): OverrideFormDefaults | undefined {
  if (params.get("ajuste") !== "1") return undefined;
  const raw = params.get("uplift")?.trim().replace(",", ".");
  const uplift = raw ? Number(raw) : NaN;
  return {
    date: params.get("mes")?.trim() || undefined,
    event_type: params.get("evento")?.trim() || undefined,
    uplift_pct: Number.isFinite(uplift) ? uplift : undefined,
    comment: params.get("comentario")?.trim() || undefined,
  };
}

export default function Forecasting() {
  const [params] = useSearchParams();
  // The hierarchy explorer became the deviation deep dive (Plano lens, broken down by region).
  if (params.get("mode") === "hierarchy")
    return <Navigate to={deviationsHref({ cmp: "fc_pl", nivel: "region" })} replace />;
  return (
    <div>
      <PageHeader
        eyebrow="Ferramentas"
        icon={<LineChart />}
        title="Workspace de forecast"
        subtitle="Uma série Cliente × SKU por vez: forecast estatístico do modelo campeão com a faixa P10–P90, consenso com os ajustes comerciais, backtest fora da amostra e o ranking de modelos da série."
        actions={<RunForecastButton />}
      />
      <SeriesWorkspace />
    </div>
  );
}

/* ================================================================ series workspace */

interface Detail {
  series_id: string;
  has_run: boolean;
  header: {
    sku: string;
    product: string;
    customer: string;
    customer_location?: string;
    region?: string;
    channel?: string;
    category?: string;
    brand?: string;
    [key: string]: unknown;
  };
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

const wmapeTone = (w: number | null | undefined): Tone =>
  w == null ? "navy" : w < 0.2 ? "green" : w < 0.35 ? "yellow" : "red";

function SeriesWorkspace() {
  const [params, setParams] = useSearchParams();
  const { filters, measure, setMeasure } = useFilters();
  const { data: list, isLoading, error: listError } = useGet<SeriesRow[]>("/api/forecast/series", filters);
  const [q, setQ] = useState("");
  const selected = params.get("series") ?? list?.[0]?.series_id ?? null;
  const prefill = overridePrefill(params);
  const {
    data: d,
    error,
    isPlaceholderData,
  } = useGet<Detail>(selected ? "/api/forecast/series-detail" : null, {
    series_id: selected ?? undefined,
    measure,
  });
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (list ?? []).filter(
      (s) =>
        !needle ||
        `${s.customer} ${s.sku} ${s.product} ${s.series_type ?? ""} ${t.seriesType(s.series_type)}`
          .toLowerCase()
          .includes(needle),
    );
  }, [list, q]);

  /** Selecting another series drops the adjustment prefill (it belongs to the linked series). */
  const select = (id: string) =>
    setParams((p) => {
      const next = new URLSearchParams(p);
      next.delete("mode");
      PREFILL_KEYS.forEach((k) => next.delete(k));
      next.set("series", id);
      return next;
    });
  /** Once the suggested adjustment is saved, a reload must not prefill it again. */
  const clearPrefill = () =>
    setParams(
      (p) => {
        const next = new URLSearchParams(p);
        PREFILL_KEYS.forEach((k) => next.delete(k));
        return next;
      },
      { replace: true },
    );

  if (isLoading) return <Loader />;
  return (
    <div>
      <FilterBar showMeasure={false} />
      <div className="grid gap-5 xl:grid-cols-[300px_minmax(0,1fr)]">
        {/* ------------------------------------------------------------ series list */}
        <aside className="card flex max-h-[440px] flex-col overflow-hidden xl:sticky xl:top-24 xl:max-h-[calc(100vh-130px)]">
          <div className="border-b border-line/70 px-4 pb-3.5 pt-4">
            <div className="flex items-center gap-3">
              <IconTile icon={<ListTree />} tone="purple" size="sm" />
              <div className="min-w-0">
                <div className="text-[15px] font-semibold tracking-tight text-ink">Séries Cliente × SKU</div>
                <div className="text-[11.5px] text-muted">
                  {filtered.length.toLocaleString("pt-BR")} {filtered.length === 1 ? "série" : "séries"} ·
                  ordenadas por receita
                </div>
              </div>
            </div>
            <div className="relative mt-3">
              <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
              <input
                className="input pl-9"
                placeholder="Buscar cliente, SKU ou produto…"
                aria-label="Buscar séries"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </div>
          </div>
          <ul className="flex-1 space-y-2 overflow-auto p-3">
            {listError && (
              <li>
                <ErrorState error={listError} />
              </li>
            )}
            {!listError && filtered.length === 0 && (
              <li className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted">
                <SearchX size={22} className="text-muted" />
                Nenhuma série encontrada.
              </li>
            )}
            {filtered.map((s) => (
              <li key={s.series_id}>
                <SeriesItem s={s} active={s.series_id === selected} onSelect={() => select(s.series_id)} />
              </li>
            ))}
          </ul>
        </aside>

        {/* ---------------------------------------------------------- series detail */}
        <div className={clsx("min-w-0 space-y-5 transition-opacity", isPlaceholderData && "opacity-60")}>
          <ErrorState error={error} />
          {!selected && (
            <div className="card">
              <EmptyState title="Nenhuma série selecionada" icon={<LineChart />}>
                Escolha uma série Cliente × SKU na lista para ver o forecast, o ranking de modelos e os
                ajustes comerciais.
              </EmptyState>
            </div>
          )}
          {selected && !d && !error && (
            <div className="card">
              <Loader />
            </div>
          )}
          {d && !d.has_run && <NoRunState />}
          {d?.selection && (
            <>
              <SeriesHeader d={d} measure={measure} setMeasure={setMeasure} />
              <Card
                icon={<ChartLine />}
                tone="blue"
                title="Real · Forecast estatístico · Consenso · Orçamento · Meta · P10–P90"
                subtitle="Clique na legenda para mostrar ou ocultar séries · linhas pontilhadas (ocultas por padrão): Desafiante e backtest fora da amostra"
              >
                <TimelineChart
                  rows={d.timeline}
                  measure={measure}
                  lastActual={lastActual(d.timeline)}
                  height={380}
                />
              </Card>
              <OverridesCard key={d.series_id} d={d} prefill={prefill} onSaved={clearPrefill} />
              <div className="grid gap-5 min-[1680px]:grid-cols-[400px_minmax(0,1fr)]">
                <ChampionCard d={d} />
                <BacktestCard d={d} />
              </div>
              <Leaderboard rows={d.leaderboard ?? []} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SeriesItem({ s, active, onSelect }: { s: SeriesRow; active: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? "true" : undefined}
      className={clsx(
        "group w-full rounded-2xl border-2 px-3.5 py-3 text-left transition duration-200",
        active
          ? "border-transparent shadow-[0_12px_26px_-14px_rgba(52,131,250,0.75)] [background:linear-gradient(135deg,#eef5ff,#ffffff)_padding-box,linear-gradient(135deg,#3483fa,#a9cbff)_border-box]"
          : "border-transparent bg-white/60 hover:-translate-y-0.5 hover:bg-white hover:shadow-[0_12px_24px_-16px_rgba(45,50,119,0.4)]",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span
          className={clsx(
            "min-w-0 break-words text-[13px] font-bold",
            active ? "text-brand-dark" : "text-ink",
          )}
        >
          {s.sku}
        </span>
        {s.wmape != null && (
          <span
            title="WMAPE do modelo campeão no backtest"
            className={clsx(
              "shrink-0 whitespace-nowrap rounded-full px-2 py-0.5 text-[10.5px] font-semibold tabular",
              TONES[wmapeTone(s.wmape)].soft,
            )}
          >
            WMAPE {pct(s.wmape, 0)}
          </span>
        )}
      </div>
      <div className="mt-0.5 break-words text-xs leading-snug text-ink-2">{s.product}</div>
      <div className="mt-1.5 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
        <span className="flex min-w-0 items-start gap-1 text-[11px] text-muted">
          <Building2 size={11} className="mt-0.5 shrink-0" />
          <span className="break-words">{s.customer}</span>
        </span>
        {s.series_type && (
          <span
            className={clsx(
              "shrink-0 whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-semibold",
              TONES.purple.soft,
            )}
          >
            {t.seriesType(s.series_type)}
          </span>
        )}
      </div>
    </button>
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
  const fmt = (v: number | null | undefined) => fmtMeasure(v, measure);
  const meta: { icon: ReactNode; label: string; value?: string }[] = [
    { icon: <Building2 />, label: "Cliente", value: h.customer },
    { icon: <MapPin />, label: "Local do cliente", value: h.customer_location },
    { icon: <MapIcon />, label: "Região", value: h.region },
    { icon: <Store />, label: "Canal", value: h.channel },
    {
      icon: <Tag />,
      label: "Categoria / Marca",
      value: [h.category, h.brand].filter(Boolean).join(" · ") || undefined,
    },
  ];
  return (
    <section className="card relative overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute -right-16 -top-24 h-64 w-64 rounded-full bg-[radial-gradient(circle,#efe9ff_0%,transparent_70%)]"
      />
      <div className="relative flex flex-wrap items-start justify-between gap-4 px-6 pb-5 pt-6">
        <div className="flex min-w-0 flex-1 items-start gap-4">
          <IconTile icon={<Package />} tone="purple" size="lg" />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-lg bg-[#eef1fa] px-2 py-0.5 font-mono text-xs font-semibold text-navy">
                {h.sku}
              </span>
              <Badge className={TONES.purple.soft}>{t.seriesType(s.series_type)}</Badge>
            </div>
            <h2 className="mt-1.5 break-words text-xl font-bold leading-snug tracking-tight text-ink">
              {h.product}
            </h2>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {meta
                .filter((m) => m.value)
                .map((m) => (
                  <span
                    key={m.label}
                    title={m.label}
                    className="inline-flex items-center gap-1.5 rounded-full border border-line bg-white/90 px-2.5 py-1 text-xs text-ink-2 [&>svg]:h-3 [&>svg]:w-3 [&>svg]:text-muted"
                  >
                    {m.icon}
                    {m.value}
                  </span>
                ))}
            </div>
            {s.classification_reason && (
              <p className="mt-2.5 max-w-3xl text-xs leading-relaxed text-muted">{s.classification_reason}</p>
            )}
          </div>
        </div>
        <Segmented<Measure>
          value={measure}
          onChange={setMeasure}
          options={[
            { value: "units", label: "Unidades" },
            { value: "revenue", label: "Receita" },
          ]}
        />
      </div>
      {/* Four stats (spec §3): Campeão · Acurácia · Viés · Faixa P10–P90. */}
      <div className="relative grid gap-3 border-t border-line/70 bg-[#f7f9ff]/70 p-4 sm:grid-cols-2 min-[1680px]:grid-cols-4">
        <HeaderStat
          icon={<Trophy />}
          tone="yellow"
          label="Modelo campeão"
          value={t.model(s.champion)}
          sub={
            <>
              <span>Confiança</span>
              <ConfidenceBadge value={s.confidence} />
            </>
          }
        />
        <HeaderStat
          icon={<Crosshair />}
          tone="green"
          label="Acurácia do forecast"
          value={pct(s.accuracy)}
          sub={`WMAPE ${pct(s.wmape)} · backtest fora da amostra`}
        />
        <HeaderStat
          icon={<Scale />}
          tone="orange"
          label="Viés"
          value={pct(s.bias, 1, true)}
          sub={
            <>
              <BiasBadge value={s.bias_class} />
              <span>positivo = superestimou</span>
            </>
          }
        />
        <HeaderStat
          icon={<ChartArea />}
          tone="teal"
          label={n ? `Faixa P10–P90 · ${monthLabel(n.date)}` : "Faixa P10–P90"}
          value={n ? `${nb(fmt(n.p10))} – ${nb(fmt(n.p90))}` : "—"}
          sub={
            n
              ? n.consensus !== n.base
                ? `Consenso ${fmt(n.consensus)} · base estatística ${fmt(n.base)}`
                : `Consenso ${fmt(n.consensus)} (= base estatística)`
              : "Empírica, fora da amostra"
          }
          small
        />
      </div>
    </section>
  );
}

function HeaderStat({
  icon,
  tone,
  label,
  value,
  sub,
  small,
}: {
  icon: ReactNode;
  tone: Tone;
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  small?: boolean;
}) {
  return (
    <div className="flex min-w-0 items-start gap-3 rounded-2xl border border-white bg-white/90 px-4 py-3.5 shadow-[0_6px_16px_-10px_rgba(45,50,119,0.25)] transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_14px_26px_-14px_rgba(45,50,119,0.35)]">
      <IconTile icon={icon} tone={tone} size="sm" />
      <div className="min-w-0 flex-1">
        <div className="text-xs font-medium leading-snug text-muted">{label}</div>
        <div
          className={clsx(
            "mt-0.5 break-words font-bold leading-tight tracking-tight text-ink tabular",
            small ? "text-base" : "text-lg",
          )}
        >
          {value}
        </div>
        {sub && (
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11.5px] leading-snug text-muted">
            {sub}
          </div>
        )}
      </div>
    </div>
  );
}

function ChampionCard({ d }: { d: Detail }) {
  const s = d.selection!;
  const champ = d.leaderboard?.find((r) => r.champion_flag);
  const chall = d.leaderboard?.find((r) => r.challenger_flag);
  const gap = s.challenger_wmape != null ? s.challenger_wmape - s.wmape : null;
  const confColor =
    s.confidence === "High" ? STATUS.good : s.confidence === "Medium" ? STATUS.warning : STATUS.critical;
  const roles: { role: string; r?: LeaderRow; icon: ReactNode; tone: Tone }[] = [
    { role: "Campeão", r: champ, icon: <Trophy />, tone: "green" },
    { role: "Desafiante", r: chall, icon: <Swords />, tone: "navy" },
  ];
  return (
    <Card
      icon={<Trophy />}
      tone="yellow"
      title="Campeão vs Desafiante"
      subtitle="Seleção por WMAPE, depois |viés| e, por fim, RMSE"
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 min-[1680px]:grid-cols-1">
          {roles.map(({ role, r, icon, tone }) =>
            r ? (
              <div
                key={role}
                className={clsx(
                  "rounded-2xl border border-white bg-gradient-to-br p-4 shadow-[0_6px_16px_-10px_rgba(45,50,119,0.25)]",
                  TONES[tone].surface,
                )}
              >
                <div className="flex items-center gap-3">
                  <IconTile icon={icon} tone={tone} size="sm" />
                  <div className="min-w-0">
                    <div className={clsx("text-[11px] font-bold uppercase tracking-wider", TONES[tone].text)}>
                      {role}
                    </div>
                    <div className="break-words font-semibold leading-snug text-ink">{t.model(r.model)}</div>
                    <div className="text-[11px] text-muted">{t.family(r.family)}</div>
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                  <MiniMetric label="WMAPE" value={pct(r.wmape)} />
                  <MiniMetric label="Viés" value={pct(r.bias, 1, true)} />
                  <MiniMetric
                    label="MASE"
                    value={
                      r.mase != null
                        ? r.mase.toLocaleString("pt-BR", {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })
                        : "—"
                    }
                  />
                </div>
              </div>
            ) : null,
          )}
        </div>

        <dl className="space-y-2.5 rounded-2xl border border-line/70 bg-white/80 p-4 text-xs">
          <div className="flex items-center justify-between gap-3">
            <dt className="text-muted">Margem do campeão</dt>
            <dd className="text-right font-semibold text-ink">
              {gap != null ? `${dec1(gap * 100)} p.p. de WMAPE` : "—"}
            </dd>
          </div>
          <div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Score de confiança</dt>
              <dd className="flex items-center gap-1.5 font-semibold text-ink">
                {s.confidence_score != null ? `${Math.round(s.confidence_score)}/100` : "—"}
                <ConfidenceBadge value={s.confidence} />
              </dd>
            </div>
            <ProgressBar value={(s.confidence_score ?? 0) / 100} color={confColor} className="mt-1.5" />
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-muted">Estabilidade (σ do WMAPE entre janelas)</dt>
            <dd className="font-semibold text-ink">{pct(s.stability, 1)}</dd>
          </div>
          <div className="flex items-center justify-between gap-3">
            <dt className="text-muted">Histórico</dt>
            <dd className="font-semibold text-ink">
              {s.history_months != null ? `${s.history_months} meses` : "—"}
            </dd>
          </div>
          <div>
            <dt className="text-muted">Modelos candidatos</dt>
            <dd className="mt-1.5 flex flex-wrap gap-1.5">
              {s.candidates.map((c) => (
                <span
                  key={c}
                  className={clsx(
                    "rounded-full px-2 py-0.5 text-[11px] font-medium",
                    c === s.champion ? TONES.green.soft : "bg-[#eef1fa] text-ink-2",
                  )}
                >
                  {t.model(c)}
                </span>
              ))}
            </dd>
          </div>
        </dl>

        {champ?.parameters && Object.keys(champ.parameters).length > 0 && (
          <details className="group rounded-2xl border border-line/70 bg-white/70 px-4 py-3 text-xs">
            <summary className="cursor-pointer font-semibold text-ink-2 marker:text-muted">
              Parâmetros do campeão
            </summary>
            <div className="mt-2 max-h-56 overflow-auto rounded-xl bg-[#f4f6fd] p-3">
              <ParamList params={champ.parameters} />
            </div>
          </details>
        )}
      </div>
    </Card>
  );
}

/** Portuguese labels for the parameter keys the models report (unknown keys pass through). */
const PARAM_LABEL: Record<string, string> = {
  season: "Período sazonal (meses)",
  window: "Janela da média (meses)",
  alpha: "α · suavização",
  beta: "β · suavização",
  phi: "φ · amortecimento",
  trend: "Tendência",
  seasonal: "Sazonalidade",
  spec: "Especificação",
  aicc: "AICc",
  order: "Ordem",
  drift: "Deriva (drift)",
  transform: "Transformação",
  size: "Tamanho médio da demanda",
  interval: "Intervalo médio entre demandas",
  prob: "Probabilidade de demanda",
  ridge: "Penalidade ridge",
  coefficients: "Coeficientes dos direcionadores",
  n_train: "Observações de treino",
  features: "Variáveis explicativas",
  min_obs: "Mínimo de observações",
  error: "Erro",
  promotion: "Promoção",
  merchandising: "Merchandising",
  log_price: "Preço (log)",
  log_distribution: "Distribuição (log)",
  log_marketing: "Marketing (log)",
  holiday: "Feriados",
  m_sin: "Sazonalidade (seno)",
  m_cos: "Sazonalidade (cosseno)",
};

const PARAM_VALUE: Record<string, string> = {
  add: "aditiva",
  mul: "multiplicativa",
  add_damped: "aditiva amortecida",
  log1p: "log(1 + x)",
};

function paramValue(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "boolean") return v ? "Sim" : "Não";
  if (typeof v === "number") return v.toLocaleString("pt-BR", { maximumFractionDigits: 4 });
  if (typeof v === "string") return PARAM_VALUE[v] ?? v;
  return String(v);
}

function ParamList({ params }: { params: Record<string, unknown> }) {
  return (
    <dl className="space-y-1.5 text-[11.5px]">
      {Object.entries(params).map(([k, v]) => {
        const nested = v != null && typeof v === "object" && !Array.isArray(v);
        return (
          <div key={k}>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-muted">{PARAM_LABEL[k] ?? k}</dt>
              {!nested && (
                <dd className="break-words text-right font-semibold text-ink tabular">
                  {Array.isArray(v) ? v.map(paramValue).join(", ") : paramValue(v)}
                </dd>
              )}
            </div>
            {nested && (
              <dd className="mt-1.5 border-t border-line/70 pt-1.5">
                {Object.keys(v as object).length > 0 ? (
                  <ParamList params={v as Record<string, unknown>} />
                ) : (
                  <span className="text-muted">—</span>
                )}
              </dd>
            )}
          </div>
        );
      })}
    </dl>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white/80 px-2 py-1.5">
      <div className="text-[10.5px] text-muted">{label}</div>
      <div className="font-bold text-ink tabular">{value}</div>
    </div>
  );
}

const MODEL_STATUS: Record<string, string> = {
  ok: "OK",
  no_backtest: "Sem backtest",
  insufficient_history: "Histórico insuficiente",
  failed: "Falhou",
};

function Leaderboard({ rows }: { rows: LeaderRow[] }) {
  return (
    <Card
      icon={<ListOrdered />}
      tone="orange"
      title="Ranking de modelos (esta série)"
      subtitle="Backtest com origem móvel e janela expansível · métricas fora da amostra"
    >
      <DataTable
        rows={rows}
        maxHeight={360}
        rowKey={(r) => r.model}
        columns={[
          {
            key: "rank",
            label: "Posição",
            align: "center",
            render: (r) =>
              r.rank ? (
                <span
                  className={clsx(
                    "inline-flex h-6 min-w-6 items-center justify-center rounded-full px-1.5 text-xs font-bold",
                    r.rank === 1
                      ? "bg-gradient-to-br from-[#fff47a] to-[#ffcf00] text-navy shadow-[0_4px_10px_-4px_rgba(240,190,0,0.8)]"
                      : "bg-[#eef1fa] text-ink-2",
                  )}
                >
                  {r.rank}
                </span>
              ) : (
                "—"
              ),
          },
          {
            key: "model",
            label: "Modelo",
            render: (r) => (
              <span className="flex flex-wrap items-center gap-1.5 font-medium text-ink">
                {t.model(r.model)}
                {r.champion_flag && (
                  <Badge className={TONES.green.soft}>
                    <Trophy size={11} /> Campeão
                  </Badge>
                )}
                {r.challenger_flag && (
                  <Badge className={TONES.navy.soft}>
                    <Swords size={11} /> Desafiante
                  </Badge>
                )}
              </span>
            ),
          },
          {
            key: "family",
            label: "Família",
            render: (r) => <span className="text-xs text-muted">{t.family(r.family)}</span>,
          },
          { key: "wmape", label: "WMAPE", align: "right", format: "percent" },
          { key: "bias", label: "Viés", align: "right", format: "percent_signed" },
          { key: "rmse", label: "RMSE", align: "right", render: (r) => units(r.rmse) },
          { key: "mase", label: "MASE", align: "right", format: "number" },
          { key: "wmape_std", label: "Estabilidade σ", align: "right", format: "percent" },
          {
            key: "status",
            label: "Status",
            render: (r) =>
              !r.status || r.status === "ok" ? (
                <Badge className={TONES.green.soft}>OK</Badge>
              ) : (
                <Badge className="bg-slate-100 text-muted">{MODEL_STATUS[r.status] ?? r.status}</Badge>
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
      icon={<History />}
      tone="teal"
      title="Backtest: forecast fora da amostra vs real"
      subtitle="Cada janela treina apenas com dados anteriores à sua origem (sem vazamento de informação) · valores em unidades"
    >
      {dates.length === 0 ? (
        <EmptyState title="Sem backtest para esta série" icon={<History />}>
          O histórico disponível não permitiu janelas de validação fora da amostra.
        </EmptyState>
      ) : (
        <SimpleLineChart
          categories={dates.map((x) => shortMonth(x))}
          series={[
            { name: "Real", data: actual, color: SERIES.actual },
            { name: `Campeão · ${t.model(s.champion)}`, data: get(s.champion), color: SERIES.base },
            ...(s.challenger
              ? [
                  {
                    name: `Desafiante · ${t.model(s.challenger)}`,
                    data: get(s.challenger),
                    color: SERIES.challenger,
                    dashed: true,
                  },
                ]
              : []),
          ]}
          format="units"
          height={330}
        />
      )}
    </Card>
  );
}

function OverridesCard({
  d,
  prefill,
  onSaved,
}: {
  d: Detail;
  /** Adjustment suggested by the deep dive (`?ajuste=1&…`). */
  prefill?: OverrideFormDefaults;
  onSaved?: () => void;
}) {
  const qc = useQueryClient();
  const ref = useRef<HTMLDivElement>(null);
  const horizon = useMemo(
    () => Array.from(new Set((d.baseline_vs_incremental ?? []).map((r) => r.date))),
    [d.baseline_vs_incremental],
  );
  const del = useMutation({
    mutationFn: (id: string) => api.del(`/api/overrides/${id}`),
    onSuccess: () => qc.invalidateQueries(),
  });
  const suggested = !!prefill;
  // A suggested adjustment is the reason the user came here: bring the form into view once.
  useEffect(() => {
    if (suggested) ref.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [suggested]);
  const overrides = d.overrides ?? [];
  return (
    <div ref={ref} className="scroll-mt-28">
      <Card
        icon={<BadgePercent />}
        tone="pink"
        title="Ajustes comerciais"
        subtitle="Eventos que afastam o consenso da base estatística · o consenso é recalculado ao salvar"
      >
        <div className="grid gap-6 min-[1680px]:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
          <div className="min-w-0">
            {suggested && (
              <div
                role="status"
                className="mb-4 flex items-start gap-3 rounded-2xl bg-[#eaf2ff] px-4 py-3 text-sm leading-snug text-[#1d3f8f]"
              >
                <ScanSearch size={18} className="mt-0.5 shrink-0" aria-hidden />
                <span>
                  Ajuste sugerido pelo deep dive dos desvios. Revise o mês, o evento e o uplift antes de
                  adicionar.
                </span>
              </div>
            )}
            <OverrideForm
              customer={d.header.customer}
              sku={d.header.sku}
              horizon={horizon}
              defaults={prefill}
              onSaved={onSaved}
            />
            <div className="mt-3 empty:hidden">
              <ErrorState error={del.error} />
            </div>
          </div>

          <div className="min-w-0">
            <div className="flex items-center justify-between">
              <span className="label-xs">Ajustes desta série</span>
              <span className="text-xs text-muted">
                {overrides.length} {overrides.length === 1 ? "ajuste" : "ajustes"}
              </span>
            </div>
            <ul className="mt-2.5 space-y-2">
              {overrides.length === 0 && (
                <li className="rounded-2xl border border-dashed border-line bg-white/50 py-6 text-center text-sm text-muted">
                  Nenhum ajuste comercial nesta série.
                </li>
              )}
              {overrides.map((o) => {
                const up = o.uplift_pct >= 0;
                const scope = !o.customer
                  ? o.sku
                    ? "Este SKU em todos os clientes"
                    : "Todas as séries"
                  : !o.sku
                    ? "Todos os SKUs do cliente"
                    : null;
                return (
                  <li
                    key={o.override_id}
                    className="flex items-start gap-3 rounded-2xl border border-line/70 bg-white/85 px-3.5 py-3 transition duration-200 hover:shadow-[0_10px_22px_-16px_rgba(45,50,119,0.4)]"
                  >
                    <IconTile
                      icon={up ? <TrendingUp /> : <TrendingDown />}
                      tone={up ? "green" : "red"}
                      size="sm"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="text-sm font-semibold text-ink">{t.event(o.event_type)}</span>
                        <Badge className={up ? TONES.green.soft : TONES.red.soft}>
                          {pct(o.uplift_pct, 0, true)}
                        </Badge>
                        <span className="text-xs text-muted">{monthLabel(o.date, "long")}</span>
                        {scope && <Badge className={TONES.navy.soft}>{scope}</Badge>}
                      </div>
                      <div className="mt-0.5 break-words text-xs text-muted">
                        {o.comment || "Sem comentário"} · {t.planner(o.created_by)}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="btn-ghost shrink-0 px-2 py-1.5 text-muted hover:text-red-600"
                      onClick={() => del.mutate(o.override_id)}
                      disabled={del.isPending}
                      aria-label="Excluir ajuste"
                      title="Excluir ajuste"
                    >
                      <Trash2 size={15} />
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      </Card>
    </div>
  );
}
