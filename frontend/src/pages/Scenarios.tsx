import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Copy,
  GitCompareArrows,
  Lock,
  Package,
  PiggyBank,
  Plus,
  Save,
  Target,
  Trash2,
  Wallet,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { BarChart, SimpleLineChart } from "../charts/BasicCharts";
import { DataTable } from "../components/DataTable";
import { useDimensions } from "../components/FilterBar";
import { NoRunState } from "../components/RunControls";
import { Badge, Card, ErrorState, Field, KpiCard, Loader, PageHeader } from "../components/ui";
import { useGet } from "../hooks/useApi";
import { useDebounced } from "../hooks/useDebounced";
import { CATEGORICAL, SERIES } from "../lib/colors";
import { money, pct, shortMonth, units } from "../lib/format";
import { api } from "../services/api";
import type { Scenario, ScenarioParams } from "../types";

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

const KIND_STYLE: Record<string, string> = {
  base: "bg-slate-100 text-slate-700",
  conservative: "bg-blue-50 text-blue-800",
  aggressive: "bg-emerald-50 text-emerald-800",
  custom: "bg-blue-50 text-blue-800",
};

interface SimResult {
  totals: Record<string, number | null>;
  monthly: Record<string, any>[];
  drivers: { lever: string; units: number }[];
}

interface CompareResult {
  rows: Record<string, any>[];
  series: { scenario_id: string; name: string; monthly: Record<string, any>[] }[];
}

export default function Scenarios() {
  const qc = useQueryClient();
  const { data: scenarios, isLoading, error } = useGet<Scenario[]>("/api/scenarios");
  const { data: dims } = useDimensions();
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<ScenarioParams>(EMPTY);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const current = scenarios?.find((s) => s.scenario_id === selected) ?? null;

  useEffect(() => {
    if (!selected && scenarios?.length)
      setSelected(scenarios.find((s) => s.kind === "aggressive")?.scenario_id ?? scenarios[0].scenario_id);
  }, [scenarios, selected]);
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
  const { data: el } = useGet<{
    estimated: Record<string, Record<string, any>>;
    synthetic_truth: Record<string, any>;
  }>("/api/scenarios/elasticities");

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
        name: name && current?.kind !== "custom" ? `${name} (custom)` : name || "Custom scenario",
        description: desc,
        params: draft,
      }),
    onSuccess: (s) => {
      setSelected(s.scenario_id);
      refresh();
    },
  });
  const dup = useMutation({
    mutationFn: (id: string) => api.post<Scenario>(`/api/scenarios/${id}/duplicate`),
    onSuccess: (s) => {
      setSelected(s.scenario_id);
      refresh();
    },
  });
  const del = useMutation({
    mutationFn: (id: string) => api.del(`/api/scenarios/${id}`),
    onSuccess: () => {
      setSelected(null);
      refresh();
    },
  });

  const horizon = dims?.horizon ?? [];
  const locked = current?.kind === "base";
  const t = sim.data?.totals;
  const set = <K extends keyof ScenarioParams>(k: K, v: ScenarioParams[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));
  const toggleMonth = (k: "promo_months" | "merch_months", m: string) =>
    set(k, draft[k].includes(m) ? draft[k].filter((x) => x !== m) : [...draft[k], m].sort());

  if (isLoading) return <Loader />;
  if (error) return <NoRunState />;
  return (
    <div>
      <PageHeader
        eyebrow="Scenario planning"
        title="Scenario Builder & What-If Engine"
        subtitle="Change price, distribution, promotion, merchandising, marketing, customer and market growth. Sensitivities are estimated from history per category."
      />
      <div className="grid gap-5 xl:grid-cols-[280px_1fr]">
        <div className="flex flex-col gap-3">
          {scenarios?.map((s) => (
            <button
              key={s.scenario_id}
              type="button"
              onClick={() => setSelected(s.scenario_id)}
              className={clsx(
                "card px-4 py-3 text-left transition hover:border-brand/40",
                selected === s.scenario_id && "border-brand ring-2 ring-brand/15",
              )}
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold">{s.name}</span>
                <Badge className={KIND_STYLE[s.kind]}>{s.kind}</Badge>
              </div>
              <p className="mt-1 line-clamp-2 text-xs text-muted">{s.description || "Custom scenario"}</p>
              {cmp && (
                <div className="mt-2 text-xs">
                  <span className="font-semibold">
                    {money(cmp.rows.find((r) => r.scenario_id === s.scenario_id)?.revenue)}
                  </span>{" "}
                  <span className="text-muted">
                    {pct(cmp.rows.find((r) => r.scenario_id === s.scenario_id)?.vs_base_revenue, 1, true)} vs
                    base
                  </span>
                </div>
              )}
            </button>
          ))}
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              setSelected(null);
              setDraft(EMPTY);
              setName("My scenario");
              setDesc("");
            }}
          >
            <Plus size={15} /> New scenario
          </button>
        </div>

        <div className="flex min-w-0 flex-col gap-5">
          <Card
            title={locked ? "Base scenario (read-only)" : "Scenario builder"}
            subtitle={
              locked
                ? "The Base scenario is the consensus forecast. Duplicate it to explore changes."
                : "Changes are simulated live; save to persist."
            }
            actions={
              <div className="flex gap-2">
                {current && (
                  <button
                    type="button"
                    className="btn-secondary px-2.5 py-1.5 text-xs"
                    onClick={() => dup.mutate(current.scenario_id)}
                  >
                    <Copy size={14} /> Duplicate
                  </button>
                )}
                {current && !current.is_system && (
                  <button
                    type="button"
                    className="btn-secondary px-2.5 py-1.5 text-xs"
                    onClick={() => del.mutate(current.scenario_id)}
                  >
                    <Trash2 size={14} /> Delete
                  </button>
                )}
                {current && !locked && (
                  <button
                    type="button"
                    className="btn-primary px-2.5 py-1.5 text-xs"
                    onClick={() => save.mutate()}
                  >
                    <Save size={14} /> Save
                  </button>
                )}
                {!locked && (
                  <button
                    type="button"
                    className="btn-secondary px-2.5 py-1.5 text-xs"
                    onClick={() => saveNew.mutate()}
                  >
                    <Plus size={14} /> Save as new
                  </button>
                )}
              </div>
            }
          >
            <fieldset disabled={locked} className={clsx(locked && "opacity-60")}>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Name">
                  <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
                </Field>
                <Field label="Description">
                  <input className="input" value={desc} onChange={(e) => setDesc(e.target.value)} />
                </Field>
              </div>
              <div className="mt-5 grid gap-x-8 gap-y-5 md:grid-cols-2 2xl:grid-cols-3">
                <Lever
                  label="Price"
                  value={draft.price_change_pct}
                  min={-0.2}
                  max={0.2}
                  onChange={(v) => set("price_change_pct", v)}
                />
                <Lever
                  label="Distribution"
                  value={draft.distribution_change_pct}
                  min={-0.3}
                  max={0.3}
                  onChange={(v) => set("distribution_change_pct", v)}
                />
                <Lever
                  label="Marketing investment"
                  value={draft.marketing_change_pct}
                  min={-0.5}
                  max={1}
                  onChange={(v) => set("marketing_change_pct", v)}
                />
                <Lever
                  label="Customer growth"
                  value={draft.customer_growth_pct}
                  min={-0.2}
                  max={0.2}
                  onChange={(v) => set("customer_growth_pct", v)}
                />
                <Lever
                  label="Market growth"
                  value={draft.market_growth_pct}
                  min={-0.1}
                  max={0.1}
                  step={0.005}
                  onChange={(v) => set("market_growth_pct", v)}
                />
                <Lever
                  label="Promo discount (revenue)"
                  value={draft.promo_discount_pct}
                  min={0}
                  max={0.4}
                  onChange={(v) => set("promo_discount_pct", v)}
                  signed={false}
                />
              </div>
              <div className="mt-5 grid gap-5 md:grid-cols-2">
                <MonthChips
                  label="Promotion ON in"
                  months={horizon}
                  selected={draft.promo_months}
                  onToggle={(m) => toggleMonth("promo_months", m)}
                  color="bg-emerald-600"
                />
                <MonthChips
                  label="Merchandising in"
                  months={horizon}
                  selected={draft.merch_months}
                  onToggle={(m) => toggleMonth("merch_months", m)}
                  color="bg-blue-600"
                />
              </div>
              <div className="mt-5 grid gap-3 md:grid-cols-5">
                {(["region", "channel", "category", "customer"] as const).map((d) => (
                  <Field key={d} label={`Scope: ${d}`}>
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
                      <option value="">All</option>
                      {((dims?.[d] as string[]) ?? []).map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </Field>
                ))}
                <Field label="Start from">
                  <select
                    className="input"
                    value={draft.base}
                    onChange={(e) => set("base", e.target.value as ScenarioParams["base"])}
                  >
                    <option value="consensus">Consensus forecast</option>
                    <option value="statistical">Statistical forecast</option>
                  </select>
                </Field>
              </div>
            </fieldset>
            <ErrorState error={save.error ?? saveNew.error ?? del.error} />
            {locked && (
              <div className="mt-3 flex items-center gap-2 text-xs text-muted">
                <Lock size={12} /> Base is the reference for every comparison.
              </div>
            )}
          </Card>

          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 2xl:grid-cols-5">
            <KpiCard
              label="Scenario revenue 12M"
              icon={<Wallet />}
              tone="green"
              value={money(t?.revenue)}
              hint={`base ${money(t?.base_revenue)}`}
            />
            <KpiCard
              label="vs Base"
              icon={<GitCompareArrows />}
              tone="blue"
              value={pct(t?.vs_base_revenue, 1, true)}
              deltaTone={(t?.vs_base_revenue ?? 0) >= 0 ? "good" : "bad"}
              delta={`${pct(t?.vs_base_units, 1, true)} units`}
            />
            <KpiCard
              label="Scenario units"
              icon={<Package />}
              tone="navy"
              value={units(t?.units)}
              hint={`base ${units(t?.base_units)}`}
            />
            <KpiCard
              label="vs Budget"
              icon={<PiggyBank />}
              tone="orange"
              value={pct(t?.vs_budget_revenue, 1, true)}
              deltaTone={(t?.vs_budget_revenue ?? 0) >= 0 ? "good" : "bad"}
              hint={money(t?.budget_revenue)}
            />
            <KpiCard
              label="vs Target"
              icon={<Target />}
              tone="yellow"
              value={pct(t?.vs_target_revenue, 1, true)}
              hint={money(t?.target_revenue)}
            />
          </div>

          <div className="grid gap-5 2xl:grid-cols-[1.4fr_1fr]">
            <Card
              title="Scenario vs base (revenue)"
              subtitle={sim.isFetching ? "Recalculating…" : "Monthly, next 12 months"}
            >
              <SimpleLineChart
                categories={(sim.data?.monthly ?? []).map((m) => shortMonth(m.date))}
                series={[
                  {
                    name: "Base",
                    data: (sim.data?.monthly ?? []).map((m) => m.base_revenue),
                    color: SERIES.base,
                  },
                  {
                    name: "Scenario",
                    data: (sim.data?.monthly ?? []).map((m) => m.scenario_revenue),
                    color: SERIES.consensus,
                  },
                  {
                    name: "Budget",
                    data: (sim.data?.monthly ?? []).map((m) => m.budget_revenue),
                    color: SERIES.budget,
                    dashed: true,
                  },
                  {
                    name: "Target",
                    data: (sim.data?.monthly ?? []).map((m) => m.target_revenue),
                    color: SERIES.target,
                    dashed: true,
                  },
                ]}
                format="currency"
                height={300}
              />
            </Card>
            <Card
              title="Impact by lever (units)"
              subtitle="Exact log-share attribution of the multiplicative model"
            >
              {sim.data?.drivers.length ? (
                <BarChart
                  categories={sim.data.drivers.map((d) => d.lever.replace("_", " "))}
                  series={[{ name: "Units", data: sim.data.drivers.map((d) => d.units) }]}
                  signColors={{ positive: "#0ca30c", negative: "#d03b3b" }}
                  horizontal
                  format="units"
                  height={300}
                />
              ) : (
                <div className="py-16 text-center text-sm text-muted">No levers changed.</div>
              )}
            </Card>
          </div>

          <ScenarioComparator cmp={cmp} />
          <ElasticityTable el={el} />
        </div>
      </div>
    </div>
  );
}

function Lever({
  label,
  value,
  min,
  max,
  step = 0.01,
  onChange,
  signed = true,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  signed?: boolean;
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-ink-2">{label}</span>
        <span
          className={clsx(
            "rounded-md px-1.5 py-0.5 text-xs font-semibold tabular",
            value > 0
              ? "bg-emerald-50 text-emerald-800"
              : value < 0
                ? "bg-red-50 text-red-800"
                : "bg-slate-100 text-slate-600",
          )}
        >
          {pct(value, 1, signed)}
        </span>
      </div>
      <input
        type="range"
        className="mt-2 w-full accent-[#3483fa]"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label={label}
      />
      <div className="flex justify-between text-[10px] text-muted">
        <span>{pct(min, 0, signed)}</span>
        <span>{pct(max, 0, signed)}</span>
      </div>
    </div>
  );
}

function MonthChips({
  label,
  months,
  selected,
  onToggle,
  color,
}: {
  label: string;
  months: string[];
  selected: string[];
  onToggle: (m: string) => void;
  color: string;
}) {
  return (
    <div>
      <div className="mb-1.5 text-xs font-semibold text-ink-2">
        {label} <span className="font-normal text-muted">({selected.length} months)</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {months.map((m) => {
          const on = selected.includes(m);
          return (
            <button
              key={m}
              type="button"
              onClick={() => onToggle(m)}
              className={clsx(
                "rounded-md border px-2 py-1 text-xs font-medium transition",
                on
                  ? `${color} border-transparent text-white`
                  : "border-line bg-white text-ink-2 hover:bg-slate-50",
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

function ScenarioComparator({ cmp }: { cmp?: CompareResult }) {
  const cats = useMemo(() => (cmp?.series[0]?.monthly ?? []).map((m) => shortMonth(m.date)), [cmp]);
  if (!cmp) return null;
  const budget = cmp.series[0]?.monthly.map((m) => m.budget_revenue) ?? [];
  const target = cmp.series[0]?.monthly.map((m) => m.target_revenue) ?? [];
  return (
    <Card
      title="Scenario comparator"
      subtitle="Revenue and units over the next 12 months vs base, budget and target"
    >
      <DataTable
        rows={cmp.rows}
        rowKey={(r) => r.scenario_id}
        columns={[
          { key: "name", label: "Scenario", render: (r) => <span className="font-medium">{r.name}</span> },
          { key: "units", label: "Units", align: "right", render: (r) => units(r.units) },
          { key: "revenue", label: "Revenue", align: "right", render: (r) => money(r.revenue) },
          { key: "vs_base_revenue", label: "vs Base", align: "right", format: "percent_signed" },
          { key: "vs_budget_revenue", label: "vs Budget", align: "right", format: "percent_signed" },
          { key: "vs_target_revenue", label: "vs Target", align: "right", format: "percent_signed" },
        ]}
      />
      <div className="mt-4">
        <SimpleLineChart
          categories={cats}
          series={[
            ...cmp.series.slice(0, 5).map((s, i) => ({
              name: s.name,
              data: s.monthly.map((m) => m.scenario_revenue),
              color: CATEGORICAL[[0, 2, 4, 6, 7][i] ?? i],
            })),
            { name: "Budget", data: budget, color: SERIES.budget, dashed: true },
            { name: "Target", data: target, color: SERIES.target, dashed: true },
          ]}
          format="currency"
          height={300}
        />
      </div>
    </Card>
  );
}

function ElasticityTable({
  el,
}: {
  el?: { estimated: Record<string, Record<string, any>>; synthetic_truth: Record<string, any> };
}) {
  if (!el) return null;
  const rows = Object.entries(el.estimated)
    .filter(([k]) => k !== "__all__")
    .map(([cat, e]) => ({ category: cat, ...e, truth_price: el.synthetic_truth.price_elasticity?.[cat] }));
  return (
    <Card
      title="Driver sensitivities (estimated from history)"
      subtitle="Pooled within-series log-log regression per category · the synthetic generator's true values are shown for validation"
    >
      <DataTable
        rows={rows}
        rowKey={(r) => r.category}
        columns={[
          { key: "category", label: "Category" },
          { key: "price_elasticity", label: "Price elasticity", align: "right", format: "number" },
          { key: "truth_price", label: "True (synthetic)", align: "right", format: "number" },
          {
            key: "distribution_elasticity",
            label: "Distribution elasticity",
            align: "right",
            format: "number",
          },
          { key: "promo_uplift", label: "Promo uplift", align: "right", format: "percent" },
          { key: "merch_uplift", label: "Merch uplift", align: "right", format: "percent" },
          { key: "marketing_elasticity", label: "Marketing elasticity", align: "right", format: "number" },
          { key: "r2", label: "R²", align: "right", format: "number" },
          { key: "n_obs", label: "Obs", align: "right", format: "number" },
          { key: "source", label: "Source" },
        ]}
      />
    </Card>
  );
}
