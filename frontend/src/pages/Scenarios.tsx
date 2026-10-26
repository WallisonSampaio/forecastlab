/**
 * "Cenários e metas" (tool): what-if scenario builder plus the goal allocation tab.
 * The deep dive's "Simular cenário" lands here with a prefilled scope and levers
 * (`ROUTES.cenarios({...})`, spec §3): a new draft opens with a banner.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Anchor,
  BadgePercent,
  ChartColumn,
  ChartLine,
  ChevronDown,
  Copy,
  FlaskConical,
  GitCompareArrows,
  Globe,
  Layers,
  Lock,
  Megaphone,
  PiggyBank,
  Plus,
  Rocket,
  Save,
  ScanSearch,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Split,
  Store,
  Tag,
  Target,
  Trash2,
  UsersRound,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { BarChart, SimpleLineChart } from "../charts/BasicCharts";
import { DataTable } from "../components/DataTable";
import { FilterBar, useDimensions, type Dimensions } from "../components/FilterBar";
import { GoalAllocation } from "../components/GoalAllocation";
import { NoRunState } from "../components/RunControls";
import {
  Badge,
  Card,
  DeltaPill,
  EmptyState,
  ErrorState,
  Field,
  IconTile,
  KpiCard,
  Loader,
  PageHeader,
  Tabs,
} from "../components/ui";
import { useGet } from "../hooks/useApi";
import { useDebounced } from "../hooks/useDebounced";
import { SERIES, TONES, type Tone } from "../lib/colors";
import { money, pct, shortMonth, units } from "../lib/format";
import { t } from "../lib/labels";
import { api, ApiError } from "../services/api";
import type { Filters, Scenario, ScenarioParams } from "../types";

const EMPTY: ScenarioParams = {
  price_change_pct: 0,
  distribution_change_pct: 0,
  promo_months: [],
  promo_discount_pct: 0.15,
  merch_months: [],
  marketing_change_pct: 0,
  customer_growth_pct: 0,
  market_growth_pct: 0,
  scope: {},
  base: "consensus",
};

const KIND: Record<string, { icon: LucideIcon; tone: Tone }> = {
  base: { icon: Anchor, tone: "navy" },
  conservative: { icon: ShieldCheck, tone: "blue" },
  aggressive: { icon: Rocket, tone: "green" },
  custom: { icon: Sparkles, tone: "purple" },
};

type ScopeDim = "region" | "channel" | "category" | "customer" | "sku";
const SCOPE_DIMS: ScopeDim[] = ["region", "channel", "category", "customer", "sku"];
const SCOPE_ALL: Record<ScopeDim, string> = {
  region: "Todas as regiões",
  channel: "Todos os canais",
  category: "Todas as categorias",
  customer: "Todos os clientes",
  sku: "Todos os SKUs",
};

/* ------------------------------------------------------------- URL prefill */

/** Query keys the deep dive may send (`ROUTES.cenarios`). */
const PREFILL_DIMS = ["region", "channel", "customer", "category", "sku"] as const;
const PREFILL_LEVERS = ["distribution_change_pct", "price_change_pct", "marketing_change_pct"] as const;
const PREFILL_NAME = "Simulação a partir do deep dive";
const PREFILL_KEYS: readonly string[] = [...PREFILL_DIMS, ...PREFILL_LEVERS];

/** A new draft from `?customer=…&distribution_change_pct=0.1`; null when the URL carries no prefill. */
function prefillFrom(sp: URLSearchParams): ScenarioParams | null {
  const scope: Filters = {};
  for (const d of PREFILL_DIMS) {
    const v = sp.get(d)?.trim();
    if (v) scope[d] = v;
  }
  const levers: Partial<Record<(typeof PREFILL_LEVERS)[number], number>> = {};
  for (const k of PREFILL_LEVERS) {
    const raw = sp.get(k)?.trim().replace(",", ".");
    const n = raw ? Number(raw) : NaN;
    if (Number.isFinite(n)) levers[k] = n;
  }
  if (!Object.keys(scope).length && !Object.keys(levers).length) return null;
  return { ...EMPTY, ...levers, scope };
}

/** "Cliente: Litoral Market · Distribuição +10,0%" — what the deep dive prefilled. */
function prefillSummary(p: ScenarioParams): string {
  const parts = PREFILL_DIMS.filter((d) => p.scope[d]).map((d) => `${t.dimension(d)}: ${p.scope[d]}`);
  const lever = (label: string, v: number) => (v ? [`${label} ${pct(v, 1, true)}`] : []);
  parts.push(
    ...lever("Distribuição", p.distribution_change_pct),
    ...lever("Preço", p.price_change_pct),
    ...lever("Marketing", p.marketing_change_pct),
  );
  return parts.join(" · ");
}

/* ------------------------------------------------------------------- types */

const SOURCE_LABEL: Record<string, string> = {
  "estimated (shrunk to prior)": "Estimada (com shrinkage)",
  estimated: "Estimada",
  default: "Padrão",
};

type Num = number | null | undefined;

interface SimTotals {
  units?: number | null;
  revenue?: number | null;
  base_units?: number | null;
  base_revenue?: number | null;
  budget_revenue?: number | null;
  target_revenue?: number | null;
  vs_base_units?: number | null;
  vs_base_revenue?: number | null;
  vs_budget_revenue?: number | null;
  vs_target_revenue?: number | null;
}

interface MonthRow {
  date: string;
  base_revenue?: number | null;
  scenario_revenue?: number | null;
  budget_revenue?: number | null;
  target_revenue?: number | null;
}

interface SimResult {
  totals: SimTotals;
  monthly: MonthRow[];
  drivers: { lever: string; units: number }[];
}

interface CompareRow {
  scenario_id: string;
  name: string;
  kind: string;
  units?: number | null;
  revenue?: number | null;
  vs_base_revenue?: number | null;
  vs_budget_revenue?: number | null;
  vs_target_revenue?: number | null;
}

interface CompareResult {
  rows: CompareRow[];
}

interface ElasticityRow {
  price_elasticity?: number | null;
  distribution_elasticity?: number | null;
  promo_uplift?: number | null;
  merch_uplift?: number | null;
  marketing_elasticity?: number | null;
  r2?: number | null;
  n_obs?: number | null;
  source?: string;
}

interface Elasticities {
  estimated: Record<string, ElasticityRow>;
  synthetic_truth: { price_elasticity?: Record<string, number> };
}

/** Green/red bars for the lever attribution chart (stable reference for the chart memo). */
const SIGN_COLORS = { positive: "#0ca30c", negative: "#d03b3b" };

/** The API answers 409 while no forecast run exists (simulate/compare need one). */
const isNoRun = (e: unknown) => e instanceof ApiError && e.status === 409;

const toneOf = (v: Num): "good" | "bad" | "neutral" => (v == null ? "neutral" : v >= 0 ? "good" : "bad");
const diff = (a: Num, b: Num) => (a != null && b != null ? a - b : null);
/** "+R$ 1,23 mi"; undefined (no pill) when the difference can't be computed. */
const signedMoney = (v: Num) => (v == null ? undefined : v > 0 ? `+${money(v)}` : money(v));

type PageTab = "simulacao" | "alocacao";

/* --------------------------------------------------------------------- page */

export default function Scenarios() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab: PageTab = params.get("tab") === "alocacao" ? "alocacao" : "simulacao";
  const setTab = (v: PageTab) =>
    setParams(
      (p) => {
        const next = new URLSearchParams(p);
        next.set("tab", v);
        return next;
      },
      { replace: true },
    );
  // Read once: a deep-dive prefill opens a brand-new (unsaved) draft.
  const [prefill] = useState(() => prefillFrom(params));
  const { data: scenarios, isLoading, error } = useGet<Scenario[]>("/api/scenarios");
  const { data: dims } = useDimensions();
  const [selected, setSelected] = useState<string | null>(null);
  /** True while the user is drafting a brand-new (unsaved) scenario. */
  const [creating, setCreating] = useState(!!prefill);
  /** The "pré-preenchido" banner stays until the user saves or picks another scenario. */
  const [fromDeepDive, setFromDeepDive] = useState(!!prefill);
  const [draft, setDraft] = useState<ScenarioParams>(prefill ?? EMPTY);
  const [name, setName] = useState(prefill ? PREFILL_NAME : "");
  const [desc, setDesc] = useState(prefill ? prefillSummary(prefill) : "");
  const current = scenarios?.find((s) => s.scenario_id === selected) ?? null;

  useEffect(() => {
    if (!selected && !creating && scenarios?.length)
      setSelected(scenarios.find((s) => s.kind === "aggressive")?.scenario_id ?? scenarios[0].scenario_id);
  }, [scenarios, selected, creating]);
  /** Once the user leaves the prefilled draft (saved it, or picked/created another), a reload must not
   * open it again: the prefill keys leave the URL (same rule as the workspace's adjustment prefill). */
  const dropPrefill = () => {
    if (PREFILL_KEYS.some((k) => params.has(k)))
      setParams(
        (p) => {
          const next = new URLSearchParams(p);
          PREFILL_KEYS.forEach((k) => next.delete(k));
          return next;
        },
        { replace: true },
      );
  };
  const pick = (id: string) => {
    setCreating(false);
    setFromDeepDive(false);
    setSelected(id);
    dropPrefill();
  };
  useEffect(() => {
    if (current) {
      setDraft({ ...EMPTY, ...current.params });
      setName(current.name);
      setDesc(current.description);
    }
  }, [current]);

  const debounced = useDebounced(draft);
  const sim = useQuery<SimResult, Error>({
    queryKey: ["simulate", debounced],
    queryFn: () => api.post<SimResult>("/api/scenarios/simulate", { params: debounced }),
    placeholderData: (p) => p,
    enabled: !!scenarios,
  });
  const { data: cmp } = useGet<CompareResult>("/api/scenarios/compare", { measure: "revenue" });
  const { data: el } = useGet<Elasticities>("/api/scenarios/elasticities");

  const refresh = () =>
    qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/api/scenarios") });
  const save = useMutation({
    mutationFn: () =>
      api.put<Scenario>(`/api/scenarios/${selected}`, { name, description: desc, params: draft }),
    onSuccess: refresh,
  });
  const saveNew = useMutation({
    mutationFn: () =>
      api.post<Scenario>("/api/scenarios", {
        name:
          name && current && current.kind !== "custom"
            ? `${name} (personalizado)`
            : name || "Cenário personalizado",
        description: desc,
        params: draft,
      }),
    onSuccess: (s) => {
      pick(s.scenario_id);
      refresh();
    },
  });
  const dup = useMutation({
    mutationFn: (id: string) => api.post<Scenario>(`/api/scenarios/${id}/duplicate`),
    onSuccess: (s) => {
      pick(s.scenario_id);
      refresh();
    },
  });
  const del = useMutation({
    mutationFn: (id: string) => api.del(`/api/scenarios/${id}`),
    onSuccess: () => {
      setCreating(false);
      setFromDeepDive(false);
      setSelected(null);
      refresh();
    },
  });

  const horizon = dims?.horizon ?? [];
  const locked = current?.kind === "base";
  const tot = sim.data?.totals;
  const monthly = sim.data?.monthly ?? [];
  const set = <K extends keyof ScenarioParams>(k: K, v: ScenarioParams[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));
  const toggleMonth = (k: "promo_months" | "merch_months", m: string) =>
    set(k, draft[k].includes(m) ? draft[k].filter((x) => x !== m) : [...draft[k], m].sort());

  const header = (
    <PageHeader
      eyebrow="Ferramentas"
      icon={<Layers />}
      title="Cenários e metas"
      subtitle="Simule preço, distribuição, promoção, merchandising, marketing e o crescimento de clientes e de mercado; depois distribua a meta. As sensibilidades são estimadas a partir do histórico de cada categoria."
    />
  );
  const tabs = (
    <div className="mb-6">
      <Tabs<PageTab>
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "simulacao", label: "Simulação de cenários", icon: <SlidersHorizontal size={16} /> },
          { value: "alocacao", label: "Alocação de metas", icon: <Split size={16} /> },
        ]}
      />
    </div>
  );
  if (isLoading) return <Loader />;
  if (isNoRun(error) || isNoRun(sim.error))
    return (
      <div>
        {header}
        <NoRunState />
      </div>
    );
  if (error)
    return (
      <div>
        {header}
        <ErrorState error={error} />
      </div>
    );
  if (tab === "alocacao")
    return (
      <div>
        {header}
        {tabs}
        <FilterBar />
        <GoalAllocation />
      </div>
    );
  return (
    <div>
      {header}
      {tabs}
      {fromDeepDive && creating && prefill && (
        <div
          role="status"
          className="mb-6 flex items-start gap-3 rounded-2xl border border-blue-200/80 bg-[#eaf2ff] px-4 py-3 text-sm leading-snug text-[#1d3f8f]"
        >
          <IconTile icon={<ScanSearch />} tone="blue" size="sm" />
          <div className="min-w-0">
            <div className="font-semibold">Cenário pré-preenchido. Ajuste e salve se quiser mantê-lo.</div>
            <div className="mt-0.5 break-words text-xs">
              Do deep dive dos desvios: {prefillSummary(prefill)}
            </div>
          </div>
        </div>
      )}
      {/* Side list only from 2xl: below that it would squeeze the builder, KPIs and tables. */}
      <div className="grid gap-6 2xl:grid-cols-[300px_minmax(0,1fr)]">
        {/* ---------------------------------------------------- scenario list */}
        <div className="grid content-start gap-3 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-1">
          <div className="label-xs col-span-full px-1">Cenários salvos</div>
          {scenarios?.map((s) => {
            const k = KIND[s.kind] ?? KIND.custom;
            const row = cmp?.rows.find((r) => r.scenario_id === s.scenario_id);
            const active = selected === s.scenario_id;
            return (
              <button
                key={s.scenario_id}
                type="button"
                onClick={() => pick(s.scenario_id)}
                className={clsx(
                  "card px-4 py-4 text-left transition duration-200 hover:-translate-y-0.5",
                  active
                    ? "bg-white ring-2 ring-brand/40 shadow-[0_18px_36px_-16px_rgba(52,131,250,0.45)]"
                    : "hover:bg-white",
                )}
              >
                <div className="flex items-start gap-3">
                  <IconTile icon={<k.icon />} tone={k.tone} size="md" />
                  <div className="min-w-0 flex-1">
                    <div className="break-words font-semibold leading-snug text-ink">{s.name}</div>
                    <Badge className={clsx("mt-1", TONES[k.tone].soft)}>{t.scenarioKind(s.kind)}</Badge>
                  </div>
                </div>
                {s.description && (
                  <p className="mt-2.5 text-xs leading-relaxed text-muted">{s.description}</p>
                )}
                {cmp && (
                  <div className="mt-3 flex flex-wrap items-end justify-between gap-2 border-t border-line pt-3">
                    <div>
                      <div className="text-[11px] text-muted">Receita 12M</div>
                      <div className="text-[15px] font-bold text-ink tabular">{money(row?.revenue)}</div>
                    </div>
                    {s.kind === "base" ? (
                      <Badge className="bg-slate-100 text-ink-2">Referência</Badge>
                    ) : (
                      <DeltaPill tone={toneOf(row?.vs_base_revenue)}>
                        {pct(row?.vs_base_revenue, 1, true)} vs base
                      </DeltaPill>
                    )}
                  </div>
                )}
              </button>
            );
          })}
          <button
            type="button"
            aria-pressed={creating}
            className={clsx(
              "flex min-h-[56px] items-center justify-center gap-2 rounded-3xl border-2 border-dashed px-4 py-3 text-sm font-semibold transition",
              creating
                ? "border-brand bg-white text-brand shadow-[0_18px_36px_-16px_rgba(52,131,250,0.45)]"
                : "border-brand/30 bg-white/50 text-brand hover:border-brand/60 hover:bg-white",
            )}
            onClick={() => {
              setCreating(true);
              setFromDeepDive(false);
              dropPrefill();
              setSelected(null);
              setDraft(EMPTY);
              setName("Meu cenário");
              setDesc("");
            }}
          >
            <Plus size={15} /> Novo cenário
          </button>
        </div>

        {/* ---------------------------------------------------- builder & results */}
        {/* Container queries: the column is narrower than the viewport, so grids follow its own width. */}
        <div className="@container flex min-w-0 flex-col gap-6">
          <Card
            title={locked ? "Cenário Base (somente leitura)" : "Construtor de cenários"}
            subtitle={
              locked
                ? "O cenário Base é o forecast de consenso. Duplique-o para explorar alterações."
                : creating
                  ? "Novo cenário: ajuste as alavancas e clique em “Salvar como novo”."
                  : "As alterações são simuladas em tempo real; salve para manter."
            }
            icon={locked ? <Lock /> : <SlidersHorizontal />}
            tone={locked ? "navy" : "blue"}
          >
            <fieldset disabled={locked} className={clsx("min-w-0", locked && "opacity-60")}>
              <div className="grid gap-4 @xl:grid-cols-2">
                <Field label="Nome">
                  <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
                </Field>
                <Field label="Descrição">
                  <input className="input" value={desc} onChange={(e) => setDesc(e.target.value)} />
                </Field>
              </div>

              <div className="mt-5 grid gap-4 @xl:grid-cols-2 @5xl:grid-cols-3">
                <LeverSlider
                  label="Preço"
                  icon={Tag}
                  tone="blue"
                  value={draft.price_change_pct}
                  min={Math.min(-0.2, draft.price_change_pct)}
                  max={Math.max(0.2, draft.price_change_pct)}
                  onChange={(v) => set("price_change_pct", v)}
                />
                <LeverSlider
                  label="Distribuição"
                  icon={Store}
                  tone="teal"
                  value={draft.distribution_change_pct}
                  min={Math.min(-0.3, draft.distribution_change_pct)}
                  max={Math.max(0.3, draft.distribution_change_pct)}
                  onChange={(v) => set("distribution_change_pct", v)}
                />
                <LeverSlider
                  label="Investimento em marketing"
                  icon={Megaphone}
                  tone="pink"
                  value={draft.marketing_change_pct}
                  min={Math.min(-0.5, draft.marketing_change_pct)}
                  max={Math.max(1, draft.marketing_change_pct)}
                  onChange={(v) => set("marketing_change_pct", v)}
                />
                <LeverSlider
                  label="Crescimento de clientes"
                  icon={UsersRound}
                  tone="purple"
                  value={draft.customer_growth_pct}
                  min={-0.2}
                  max={0.2}
                  onChange={(v) => set("customer_growth_pct", v)}
                />
                <LeverSlider
                  label="Crescimento de mercado"
                  icon={Globe}
                  tone="green"
                  value={draft.market_growth_pct}
                  min={-0.1}
                  max={0.1}
                  step={0.005}
                  onChange={(v) => set("market_growth_pct", v)}
                />
                <LeverSlider
                  label="Desconto promocional (receita)"
                  icon={BadgePercent}
                  tone="orange"
                  value={draft.promo_discount_pct}
                  min={0}
                  max={0.4}
                  onChange={(v) => set("promo_discount_pct", v)}
                  signed={false}
                />
              </div>

              <div className="mt-4 grid gap-4 @3xl:grid-cols-2">
                <MonthChips
                  label="Promoção ativa em"
                  icon={Sparkles}
                  tone="green"
                  months={horizon}
                  selected={draft.promo_months}
                  onToggle={(m) => toggleMonth("promo_months", m)}
                  activeClass="from-[#16b36b] to-[#3fd08e] shadow-[0_6px_14px_-6px_rgba(22,179,107,0.8)]"
                />
                <MonthChips
                  label="Merchandising em"
                  icon={Store}
                  tone="blue"
                  months={horizon}
                  selected={draft.merch_months}
                  onToggle={(m) => toggleMonth("merch_months", m)}
                  activeClass="from-[#3483fa] to-[#5b9cff] shadow-[0_6px_14px_-6px_rgba(52,131,250,0.8)]"
                />
              </div>

              {/* At most 3 per row: more selects in one row cut long customer names. */}
              <div className="mt-5 grid gap-3 @lg:grid-cols-2 @3xl:grid-cols-3">
                {SCOPE_DIMS.map((d) => (
                  <Field key={d} label={`Escopo: ${d === "sku" ? "SKU" : t.dimension(d).toLowerCase()}`}>
                    <select
                      className="input"
                      value={draft.scope[d] ?? ""}
                      onChange={(e) => {
                        const scope = { ...draft.scope };
                        if (e.target.value) scope[d] = e.target.value;
                        else delete scope[d];
                        set("scope", scope);
                      }}
                    >
                      <option value="">{SCOPE_ALL[d]}</option>
                      {scopeOptions(dims, d, draft.scope[d]).map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                ))}
                <Field label="Partir de">
                  <select
                    className="input"
                    value={draft.base}
                    onChange={(e) => set("base", e.target.value as ScenarioParams["base"])}
                  >
                    <option value="consensus">Forecast de consenso</option>
                    <option value="statistical">Forecast estatístico</option>
                  </select>
                </Field>
              </div>
            </fieldset>

            <ErrorState error={save.error ?? saveNew.error ?? del.error ?? dup.error ?? sim.error} />

            <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
              <div className="flex items-center gap-2 text-xs text-muted">
                {locked ? (
                  <>
                    <Lock size={13} /> O Base é a referência para todas as comparações.
                  </>
                ) : sim.isFetching ? (
                  <>
                    <span className="h-2 w-2 animate-pulse rounded-full bg-brand" /> Recalculando a simulação…
                  </>
                ) : (
                  <>
                    <span className="h-2 w-2 rounded-full bg-emerald-500" /> Simulação atualizada
                  </>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {current && (
                  <button
                    type="button"
                    className="btn-secondary px-3 py-2 text-xs"
                    onClick={() => dup.mutate(current.scenario_id)}
                    disabled={dup.isPending}
                  >
                    <Copy size={14} /> Duplicar
                  </button>
                )}
                {current && !current.is_system && (
                  <button
                    type="button"
                    className="btn-secondary px-3 py-2 text-xs text-red-700"
                    onClick={() => {
                      if (window.confirm(`Excluir o cenário "${current.name}"?`))
                        del.mutate(current.scenario_id);
                    }}
                    disabled={del.isPending}
                  >
                    <Trash2 size={14} /> Excluir
                  </button>
                )}
                {!locked && (
                  <button
                    type="button"
                    className={clsx(
                      creating ? "btn-primary px-3.5 py-2 text-xs" : "btn-secondary px-3 py-2 text-xs",
                    )}
                    onClick={() => saveNew.mutate()}
                    disabled={saveNew.isPending}
                  >
                    <Plus size={14} /> Salvar como novo
                  </button>
                )}
                {current && !locked && (
                  <button
                    type="button"
                    className="btn-primary px-3.5 py-2 text-xs"
                    onClick={() => save.mutate()}
                    disabled={save.isPending}
                  >
                    <Save size={14} /> Salvar
                  </button>
                )}
              </div>
            </div>
          </Card>

          {/* 4 KPIs (units live in the revenue hint): 2 per row, 4 once the column is ≥ 1152px wide. */}
          <div className="grid gap-4 @xl:grid-cols-2 @6xl:grid-cols-4">
            <KpiCard
              label="Receita do cenário 12M"
              icon={<Wallet />}
              tone="green"
              value={money(tot?.revenue)}
              hint={`${units(tot?.units)} unidades · base ${money(tot?.base_revenue)}`}
            />
            <KpiCard
              label="Cenário vs base"
              icon={<GitCompareArrows />}
              tone="blue"
              value={pct(tot?.vs_base_revenue, 1, true)}
              delta={
                tot?.vs_base_units == null ? undefined : `${pct(tot.vs_base_units, 1, true)} em unidades`
              }
              deltaTone={toneOf(tot?.vs_base_units)}
              hint="em receita"
            />
            <KpiCard
              label="Cenário vs orçamento"
              icon={<PiggyBank />}
              tone="orange"
              value={pct(tot?.vs_budget_revenue, 1, true)}
              delta={signedMoney(diff(tot?.revenue, tot?.budget_revenue))}
              deltaTone={toneOf(tot?.vs_budget_revenue)}
              hint={`Orçamento ${money(tot?.budget_revenue)}`}
            />
            <KpiCard
              label="Cenário vs meta"
              icon={<Target />}
              tone="yellow"
              value={pct(tot?.vs_target_revenue, 1, true)}
              delta={signedMoney(diff(tot?.revenue, tot?.target_revenue))}
              deltaTone={toneOf(tot?.vs_target_revenue)}
              hint={`Meta ${money(tot?.target_revenue)}`}
            />
          </div>

          <div className="grid gap-6 @5xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
            <Card
              title="Cenário vs base (receita)"
              subtitle={sim.isFetching ? "Recalculando…" : "Mensal, próximos 12 meses"}
              icon={<ChartLine />}
              tone="blue"
            >
              <SimpleLineChart
                categories={monthly.map((m) => shortMonth(m.date))}
                series={[
                  { name: "Base", data: monthly.map((m) => m.base_revenue ?? null), color: SERIES.base },
                  {
                    name: "Cenário",
                    data: monthly.map((m) => m.scenario_revenue ?? null),
                    color: SERIES.consensus,
                  },
                  {
                    name: "Orçamento",
                    data: monthly.map((m) => m.budget_revenue ?? null),
                    color: SERIES.budget,
                    dashed: true,
                  },
                  {
                    name: "Meta",
                    data: monthly.map((m) => m.target_revenue ?? null),
                    color: SERIES.target,
                    dashed: true,
                  },
                ]}
                format="currency"
                height={300}
              />
            </Card>
            <Card
              title="Impacto por alavanca (unidades)"
              subtitle="Atribuição exata por participação logarítmica do modelo multiplicativo"
              icon={<ChartColumn />}
              tone="purple"
            >
              {sim.data?.drivers.length ? (
                <BarChart
                  categories={sim.data.drivers.map((d) => t.lever(d.lever))}
                  series={[{ name: "Unidades", data: sim.data.drivers.map((d) => d.units) }]}
                  signColors={SIGN_COLORS}
                  horizontal
                  format="units"
                  height={300}
                />
              ) : (
                <EmptyState title="Nenhuma alavanca alterada" icon={<SlidersHorizontal />}>
                  Mova os controles acima para ver o impacto de cada alavanca.
                </EmptyState>
              )}
            </Card>
          </div>

          <ScenarioComparator cmp={cmp} />
          <ModelAssumptions el={el} />
        </div>
      </div>
    </div>
  );
}

/** Options of a scope select; a prefilled value missing from the dimension list is kept selectable. */
function scopeOptions(dims: Dimensions | undefined, d: ScopeDim, current?: string) {
  const opts =
    d === "sku"
      ? (dims?.sku ?? []).map((s) => ({ value: s.sku, label: `${s.sku} · ${s.product}` }))
      : (dims?.[d] ?? []).map((v) => ({ value: v, label: v }));
  return current && !opts.some((o) => o.value === current)
    ? [{ value: current, label: current }, ...opts]
    : opts;
}

/* --------------------------------------------------------------- lever slider */
function LeverSlider({
  label,
  icon: Icon,
  tone,
  value,
  min,
  max,
  step = 0.01,
  onChange,
  signed = true,
}: {
  label: string;
  icon: LucideIcon;
  tone: Tone;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  signed?: boolean;
}) {
  const span = max - min || 1;
  const pos = ((value - min) / span) * 100;
  const zero = signed ? ((0 - min) / span) * 100 : 0;
  const a = Math.max(0, Math.min(pos, zero));
  const b = Math.min(100, Math.max(pos, zero));
  const track = `linear-gradient(to right, #e6ebf7 0%, #e6ebf7 ${a}%, #3483fa ${a}%, #5b9cff ${b}%, #e6ebf7 ${b}%, #e6ebf7 100%)`;
  return (
    <div className="rounded-2xl border border-line/80 bg-white/70 p-4 shadow-[0_4px_14px_-10px_rgba(45,50,119,0.25)]">
      <div className="flex items-center gap-3">
        <IconTile icon={<Icon />} tone={tone} size="sm" />
        <span className="min-w-0 flex-1 text-[13px] font-semibold leading-snug text-ink">{label}</span>
        <span
          className={clsx(
            "shrink-0 rounded-full px-2.5 py-0.5 text-xs font-bold tabular",
            !signed
              ? "bg-[#eaf2ff] text-[#2364d2]"
              : value > 0
                ? "bg-emerald-50 text-emerald-700"
                : value < 0
                  ? "bg-red-50 text-red-700"
                  : "bg-slate-100 text-ink-2",
          )}
        >
          {pct(value, 1, signed)}
        </span>
      </div>
      <input
        type="range"
        className={clsx(
          "mt-4 h-2 w-full cursor-pointer appearance-none rounded-full accent-[#3483fa] outline-none disabled:cursor-not-allowed",
          "focus-visible:ring-4 focus-visible:ring-brand/15",
          "[&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-[3px] [&::-webkit-slider-thumb]:border-[#3483fa] [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:shadow-[0_4px_10px_-2px_rgba(52,131,250,0.65)]",
          "[&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-[3px] [&::-moz-range-thumb]:border-[#3483fa] [&::-moz-range-thumb]:bg-white [&::-moz-range-thumb]:shadow-[0_4px_10px_-2px_rgba(52,131,250,0.65)]",
          "[&::-moz-range-track]:bg-transparent",
        )}
        style={{ background: track }}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label={label}
        aria-valuetext={pct(value, 1, signed)}
      />
      <div className="mt-1.5 flex justify-between text-[10.5px] font-medium text-muted tabular">
        <span>{pct(min, 0, signed)}</span>
        {signed && min < 0 && <span>0%</span>}
        <span>{pct(max, 0, signed)}</span>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- month chips */
function MonthChips({
  label,
  icon: Icon,
  tone,
  months,
  selected,
  onToggle,
  activeClass,
}: {
  label: string;
  icon: LucideIcon;
  tone: Tone;
  months: string[];
  selected: string[];
  onToggle: (m: string) => void;
  activeClass: string;
}) {
  const n = selected.length;
  return (
    <div className="rounded-2xl border border-line/80 bg-white/70 p-4 shadow-[0_4px_14px_-10px_rgba(45,50,119,0.25)]">
      <div className="mb-3 flex items-center gap-3">
        <IconTile icon={<Icon />} tone={tone} size="sm" />
        <span className="flex-1 text-[13px] font-semibold text-ink">{label}</span>
        <Badge className={TONES[tone].soft}>
          {n} {n === 1 ? "mês" : "meses"}
        </Badge>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {months.map((m) => {
          const on = selected.includes(m);
          return (
            <button
              key={m}
              type="button"
              aria-pressed={on}
              onClick={() => onToggle(m)}
              className={clsx(
                "rounded-full px-3 py-1 text-xs font-semibold transition",
                on
                  ? clsx("bg-gradient-to-r text-white", activeClass)
                  : "border border-line bg-white text-ink-2 hover:border-brand/40 hover:text-ink",
              )}
            >
              {shortMonth(m)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ comparator */
function ScenarioComparator({ cmp }: { cmp?: CompareResult }) {
  if (!cmp) return null;
  return (
    <Card
      title="Comparador de cenários"
      subtitle="Receita e unidades nos próximos 12 meses vs base, orçamento e meta"
      icon={<GitCompareArrows />}
      tone="navy"
    >
      <DataTable
        rows={cmp.rows}
        rowKey={(r) => r.scenario_id}
        columns={[
          {
            key: "name",
            label: "Cenário",
            render: (r) => {
              const k = KIND[r.kind] ?? KIND.custom;
              return (
                <span className="flex items-center gap-2.5">
                  <IconTile icon={<k.icon />} tone={k.tone} size="sm" />
                  <span className="min-w-[120px] whitespace-normal font-semibold leading-snug text-ink">
                    {r.name}
                  </span>
                </span>
              );
            },
          },
          { key: "units", label: "Unidades", align: "right", render: (r) => units(r.units) },
          {
            key: "revenue",
            label: "Receita",
            align: "right",
            render: (r) => <b className="text-ink">{money(r.revenue)}</b>,
          },
          { key: "vs_base_revenue", label: "vs Base", align: "right", format: "percent_signed" },
          { key: "vs_budget_revenue", label: "vs Orçamento", align: "right", format: "percent_signed" },
          { key: "vs_target_revenue", label: "vs Meta", align: "right", format: "percent_signed" },
        ]}
      />
    </Card>
  );
}

/* ------------------------------------------- model assumptions (elasticities) */
function ModelAssumptions({ el }: { el?: Elasticities }) {
  if (!el) return null;
  const rows = Object.entries(el.estimated)
    .filter(([k]) => k !== "__all__")
    .map(([cat, e]) => ({
      category: cat,
      ...e,
      truth_price: el.synthetic_truth.price_elasticity?.[cat] ?? null,
    }));
  return (
    <details className="card group px-6 py-5">
      <summary className="flex cursor-pointer list-none items-center gap-3 [&::-webkit-details-marker]:hidden">
        <IconTile icon={<FlaskConical />} tone="teal" size="sm" />
        <span className="min-w-0 flex-1">
          <span className="block text-[15px] font-semibold tracking-tight text-ink">Premissas do modelo</span>
          <span className="mt-0.5 block text-xs leading-relaxed text-muted">
            Sensibilidades usadas na simulação: regressão log-log agrupada (efeito fixo por série) em cada
            categoria · os valores verdadeiros do gerador sintético aparecem para validação
          </span>
        </span>
        <ChevronDown size={18} className="shrink-0 text-muted transition group-open:rotate-180" aria-hidden />
      </summary>
      {/* 10 columns: let the long headers break into two lines so the table needs less width. */}
      <div className="mt-4 [&_th]:align-bottom [&_th]:leading-snug [&_th>span]:whitespace-normal">
        <DataTable
          rows={rows}
          rowKey={(r) => r.category}
          columns={[
            {
              key: "category",
              label: "Categoria",
              render: (r) => <span className="font-semibold text-ink">{r.category}</span>,
            },
            { key: "price_elasticity", label: "Elasticidade-preço", align: "right", format: "number" },
            { key: "truth_price", label: "Verdadeira (sintética)", align: "right", format: "number" },
            {
              key: "distribution_elasticity",
              label: "Elasticidade-distribuição",
              align: "right",
              format: "number",
            },
            { key: "promo_uplift", label: "Uplift promocional", align: "right", format: "percent" },
            { key: "merch_uplift", label: "Uplift merchandising", align: "right", format: "percent" },
            {
              key: "marketing_elasticity",
              label: "Elasticidade-marketing",
              align: "right",
              format: "number",
            },
            { key: "r2", label: "R²", align: "right", format: "number" },
            { key: "n_obs", label: "Obs.", align: "right", format: "number" },
            {
              key: "source",
              label: "Origem",
              render: (r) =>
                r.source ? (
                  <Badge className={r.source === "default" ? "bg-slate-100 text-ink-2" : TONES.teal.soft}>
                    {SOURCE_LABEL[r.source] ?? r.source}
                  </Badge>
                ) : (
                  "—"
                ),
            },
          ]}
        />
      </div>
    </details>
  );
}
