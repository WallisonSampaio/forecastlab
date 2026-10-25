import { AlertTriangle, ArrowRight, Gauge, Package, Scale, Target, TrendingUp, Wallet } from "lucide-react";
import { Link } from "react-router-dom";

import { BarChart } from "../charts/BasicCharts";
import { TimelineChart } from "../charts/TimelineChart";
import { FilterBar } from "../components/FilterBar";
import { ExportMenu, NoRunState, RunForecastButton } from "../components/RunControls";
import {
  BiasBadge,
  Card,
  ClassBadge,
  ErrorState,
  KpiCard,
  Loader,
  PageHeader,
  SeverityBadge,
} from "../components/ui";
import { useGet } from "../hooks/useApi";
import { useFilters } from "../hooks/useFilters";
import { CLASS_STYLE } from "../lib/colors";
import { money, pct } from "../lib/format";
import type { Alert, Feasibility, TimelineRow } from "../types";

interface OverviewData {
  has_run: boolean;
  n_series: number;
  last_actual: string;
  run_id: string | null;
  dataset_version: string;
  kpis?: {
    accuracy: number;
    wmape: number;
    bias: number;
    bias_class: string;
    revenue_forecast: number;
    revenue_statistical: number;
    revenue_ltm: number;
    budget: number;
    target: number;
    budget_gap: number;
    budget_gap_pct: number;
    target_gap: number;
    target_gap_pct: number;
    risk_skus: number;
    overforecasted_series: number;
    overforecasted_skus: number;
  };
  timeline?: TimelineRow[];
  series_types?: { type: string; count: number }[];
  champions?: { model: string; count: number }[];
  confidence?: { level: string; count: number }[];
  alerts?: Alert[];
  alert_counts?: Record<string, number>;
  feasibility?: Feasibility;
}

export default function Overview() {
  const { filters } = useFilters();
  const { data, isLoading, error } = useGet<OverviewData>("/api/overview", filters);
  const k = data?.kpis;
  const f = data?.feasibility;
  return (
    <div>
      <PageHeader
        eyebrow="Executive overview"
        title="Demand Plan at a Glance"
        subtitle={
          data
            ? `${data.n_series} Customer × SKU series · last actual ${data.last_actual.slice(0, 7)} · 12-month horizon · revenue in R$`
            : undefined
        }
        actions={
          <>
            <ExportMenu />
            <RunForecastButton />
          </>
        }
      />
      <FilterBar showMeasure={false} />
      <ErrorState error={error} />
      {isLoading && <Loader />}
      {data && !data.has_run && <NoRunState />}
      {k && (
        <>
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
            <KpiCard
              label="Forecast Accuracy"
              value={pct(k.accuracy)}
              hint="1 − WMAPE · rolling-origin backtest"
              icon={<Gauge size={16} />}
              accent="#1baf7a"
            />
            <KpiCard
              label="WMAPE"
              value={pct(k.wmape)}
              hint="Weighted error, last 12 months"
              icon={<Scale size={16} />}
            />
            <KpiCard
              label="Bias"
              value={pct(k.bias, 1, true)}
              delta={<BiasBadge value={k.bias_class} />}
              icon={<TrendingUp size={16} />}
            />
            <KpiCard
              label="Revenue Forecast 12M"
              value={money(k.revenue_forecast)}
              delta={`${pct(k.revenue_forecast / k.revenue_ltm - 1, 1, true)} vs LTM`}
              deltaTone={k.revenue_forecast >= k.revenue_ltm ? "good" : "bad"}
              hint="Consensus"
              icon={<Wallet size={16} />}
              accent="#2a78d6"
            />
            <KpiCard
              label="Budget Gap"
              value={money(k.budget_gap)}
              delta={pct(k.budget_gap_pct, 1, true)}
              deltaTone={k.budget_gap >= 0 ? "good" : "bad"}
              hint={`Budget ${money(k.budget)}`}
              accent="#eb6834"
            />
            <KpiCard
              label="Target Gap"
              value={money(k.target_gap)}
              delta={pct(k.target_gap_pct, 1, true)}
              deltaTone={k.target_gap >= 0 ? "good" : "bad"}
              hint={`Target ${money(k.target)}`}
              icon={<Target size={16} />}
              accent="#eda100"
            />
            <KpiCard
              label="Risk SKUs"
              value={k.risk_skus}
              hint="SKUs with high/critical alerts"
              icon={<AlertTriangle size={16} />}
              accent="#d03b3b"
            />
            <KpiCard
              label="Overforecasted SKUs"
              value={k.overforecasted_skus}
              hint={`${k.overforecasted_series} series with bias > +5%`}
              icon={<Package size={16} />}
            />
          </div>

          <div className="mt-5 grid gap-5 xl:grid-cols-[1fr_380px]">
            <Card
              title="Revenue plan — actual, statistical, consensus, budget & target"
              subtitle="Shaded band = P10–P90 statistical range. Click the legend to toggle series."
            >
              <TimelineChart
                rows={data.timeline ?? []}
                measure="revenue"
                lastActual={data.last_actual}
                height={360}
              />
            </Card>
            <div className="flex flex-col gap-5">
              {f?.available && (
                <Card
                  title="Is the 12-month target realistic?"
                  actions={
                    <Link to="/app/sop" className="text-xs font-medium text-brand hover:underline">
                      S&OP cockpit →
                    </Link>
                  }
                >
                  <div className="flex items-center justify-between">
                    <ClassBadge value={f.classification} large />
                    <div className="text-right">
                      <div className="text-2xl font-semibold">{pct(f.probability, 0)}</div>
                      <div className="text-[11px] text-muted">probability to hit target</div>
                    </div>
                  </div>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${f.probability * 100}%`,
                        background: CLASS_STYLE[f.classification]?.color,
                      }}
                    />
                  </div>
                  <p className="mt-3 text-xs leading-relaxed text-ink-2">{f.recommendation}</p>
                </Card>
              )}
              <Card
                title="Alert center"
                subtitle={`${data.alert_counts?.high ?? 0} high · ${data.alert_counts?.medium ?? 0} medium`}
                actions={
                  <Link to="/app/alerts" className="text-xs font-medium text-brand hover:underline">
                    All alerts →
                  </Link>
                }
              >
                <ul className="divide-y divide-slate-100">
                  {(data.alerts ?? []).slice(0, 5).map((a) => (
                    <li key={a.id} className="py-2.5">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-medium">
                          <span aria-hidden>{a.icon}</span> {a.title}
                        </span>
                        <SeverityBadge value={a.severity} />
                      </div>
                      <div className="mt-0.5 truncate text-xs text-muted">
                        {[a.entity.customer, a.entity.sku, a.entity.product].filter(Boolean).join(" · ")} —{" "}
                        {a.magnitude}
                      </div>
                    </li>
                  ))}
                </ul>
              </Card>
            </div>
          </div>

          <div className="mt-5 grid gap-5 lg:grid-cols-3">
            <Card title="Demand patterns" subtitle="Series type classification">
              <BarChart
                categories={(data.series_types ?? []).map((s) => s.type)}
                series={[
                  { name: "Series", data: (data.series_types ?? []).map((s) => s.count), color: "#2a78d6" },
                ]}
                horizontal
                format="number"
                height={300}
              />
            </Card>
            <Card title="Champion models" subtitle="Best model per series after backtesting">
              <BarChart
                categories={(data.champions ?? []).map((s) => s.model)}
                series={[
                  { name: "Series", data: (data.champions ?? []).map((s) => s.count), color: "#2a78d6" },
                ]}
                horizontal
                format="number"
                height={300}
              />
            </Card>
            <Card title="Model confidence" subtitle="Error, stability, history depth and champion margin">
              <div className="space-y-3 pt-2">
                {["High", "Medium", "Low"].map((lvl) => {
                  const n = data.confidence?.find((c) => c.level === lvl)?.count ?? 0;
                  const share = data.n_series ? n / data.n_series : 0;
                  const color = lvl === "High" ? "#0ca30c" : lvl === "Medium" ? "#fab219" : "#d03b3b";
                  return (
                    <div key={lvl}>
                      <div className="flex justify-between text-sm">
                        <span className="font-medium">{lvl} confidence</span>
                        <span className="text-muted">
                          {n} series · {pct(share, 0)}
                        </span>
                      </div>
                      <div className="mt-1 h-2 rounded-full bg-slate-100">
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${share * 100}%`, background: color }}
                        />
                      </div>
                    </div>
                  );
                })}
                <Link
                  to="/app/models"
                  className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline"
                >
                  Model performance center <ArrowRight size={12} />
                </Link>
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
