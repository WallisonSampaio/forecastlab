import clsx from "clsx";
import type { LucideIcon } from "lucide-react";
import {
  Bell,
  BellRing,
  CircleDollarSign,
  Crosshair,
  ExternalLink,
  Flame,
  Layers,
  Rocket,
  ScanSearch,
  Search,
  ShieldAlert,
  Sparkles,
  Swords,
  Target,
  TrendingDown,
  TrendingUp,
  Waypoints,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { NoRunState } from "../components/RunControls";
import { Card, EmptyState, IconTile, KpiCard, Loader, PageHeader, SeverityBadge } from "../components/ui";
import { useGet } from "../hooks/useApi";
import { TONES, type Tone } from "../lib/colors";
import { deviationsHref } from "../lib/deviationsUrl";
import { money } from "../lib/format";
import { t } from "../lib/labels";
import { ROUTES } from "../lib/routes";
import type { Alert } from "../types";

interface AlertsData {
  summary: { total: number; by_severity: Record<string, number>; by_type: Record<string, number> };
  alerts: Alert[];
}

/** Display metadata per alert type code (codes stay English in the API). */
const TYPE_META: Record<string, { label: string; en: string; tone: Tone; icon: LucideIcon }> = {
  high_error: { label: "Erro de forecast elevado", en: "High Forecast Error", tone: "red", icon: Crosshair },
  severe_over: { label: "Superestimação severa", en: "Severe Overforecast", tone: "red", icon: TrendingUp },
  severe_under: {
    label: "Subestimação severa",
    en: "Severe Underforecast",
    tone: "blue",
    icon: TrendingDown,
  },
  target_above_p90: { label: "Meta acima do P90", en: "Target Above P90", tone: "orange", icon: Target },
  structural_change: {
    label: "Mudança estrutural no forecast",
    en: "Forecast Structural Change",
    tone: "orange",
    icon: Waypoints,
  },
  challenger_improving: {
    label: "Desafiante melhorando",
    en: "Challenger Model Improving",
    tone: "yellow",
    icon: Swords,
  },
  opportunity: { label: "Oportunidade comercial", en: "Commercial Opportunity", tone: "green", icon: Rocket },
};
const TYPE_ORDER = Object.keys(TYPE_META);
const SEVERITIES = ["critical", "high", "medium", "low"] as const;
const SEVERITY_DOT: Record<string, string> = {
  critical: "bg-red-500",
  high: "bg-orange-500",
  medium: "bg-amber-400",
  low: "bg-slate-400",
};

const metaOf = (type: string) =>
  TYPE_META[type] ?? { label: type, en: type, tone: "navy" as Tone, icon: Bell };

/** The backend may still send the English title; show the Portuguese label in that case. */
const titleOf = (a: Alert) => {
  const m = TYPE_META[a.type];
  return !a.title || (m && a.title === m.en) ? metaOf(a.type).label : a.title;
};

/** Portuguese question for the AI analyst, phrased so the intent parser routes it correctly. */
function analystQuestion(a: Alert): string {
  const sku = a.entity.sku;
  const customer = a.entity.customer;
  const where = [sku && `para ${sku}`, customer && `em ${customer}`].filter(Boolean).join(" ");
  const of = customer ? ` de ${customer}` : "";
  switch (a.type) {
    case "target_above_p90":
      return `A meta${of} é realista?`;
    case "severe_over":
      return `Quais SKUs${of} estão superestimados?`;
    case "severe_under":
      return `Quais SKUs${of} estão subestimados?`;
    case "structural_change":
      return `Por que o forecast${sku ? ` de ${sku}` : ""}${customer ? ` em ${customer}` : ""} mudou?`;
    case "opportunity":
      return `Quais são os principais riscos e oportunidades${customer ? ` para ${customer}` : ""}?`;
    default:
      return `Qual modelo tem o melhor desempenho${where ? ` ${where}` : ""}?`;
  }
}

/** Series-level forecast-error alerts open the Previsão lens on that series (drawer open). */
const SERIES_ERROR_TYPES = new Set(["high_error", "severe_over", "severe_under", "structural_change"]);

/**
 * "Investigar no deep dive" target per alert type (spec §3). `challenger_improving` is a model
 * decision, not a deviation: it has no deep-dive link and keeps the workspace link.
 */
function deepDiveHref(a: Alert): string | null {
  const { customer, sku, series_id } = a.entity;
  if (SERIES_ERROR_TYPES.has(a.type) && customer && sku)
    return deviationsHref({
      cmp: "ac_fc",
      path: { customer, sku },
      nivel: "series",
      serie: series_id || `${customer}|${sku}`,
    });
  if (a.type === "target_above_p90" && customer)
    return deviationsHref({ cmp: "fc_tg", path: { customer }, nivel: "category" });
  if (a.type === "opportunity" && customer)
    return deviationsHref({ cmp: "fc_pl", path: { customer }, nivel: "category" });
  return null;
}

const PRIMARY_LINK =
  "inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-[#3483fa] to-[#5b9cff] px-3.5 py-1.5 text-xs font-semibold text-white shadow-[0_8px_18px_-10px_rgba(52,131,250,0.9)] transition hover:brightness-105";
const SECONDARY_LINK =
  "inline-flex items-center gap-1.5 rounded-full border border-line bg-white/90 px-3.5 py-1.5 text-xs font-semibold text-ink-2 transition hover:bg-white hover:text-brand";

const ENTITY_FIELDS = ["customer", "sku", "product", "region"] as const;

export default function Alerts() {
  const [type, setType] = useState<string>("");
  const [severity, setSeverity] = useState<string>("");
  const { data, isLoading } = useGet<AlertsData>("/api/alerts", {
    type: type || undefined,
    severity: severity || undefined,
  });
  if (isLoading) return <Loader />;
  if (!data) return <NoRunState />;
  const { summary, alerts } = data;
  const impact = alerts.reduce((s, a) => s + (a.potential_impact ?? 0), 0);
  const types = [
    ...TYPE_ORDER.filter((k) => k in summary.by_type),
    ...Object.keys(summary.by_type).filter((k) => !TYPE_ORDER.includes(k)),
  ];

  return (
    <div>
      <PageHeader
        eyebrow="Central de alertas"
        icon={<BellRing />}
        title="Exceções que precisam de atenção"
        subtitle="Cada alerta explica o problema, a entidade afetada, a magnitude, o impacto potencial e o que investigar primeiro."
      />

      <div className="mb-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Alertas ativos"
          value={summary.total.toLocaleString("pt-BR")}
          hint="em todo o portfólio"
          icon={<Bell />}
          tone="blue"
        />
        <KpiCard
          label="Críticos"
          value={(summary.by_severity.critical ?? 0).toLocaleString("pt-BR")}
          hint="ação imediata"
          icon={<Flame />}
          tone="red"
        />
        <KpiCard
          label="Severidade alta"
          value={(summary.by_severity.high ?? 0).toLocaleString("pt-BR")}
          hint="revisar nesta semana"
          icon={<ShieldAlert />}
          tone="orange"
        />
        <KpiCard
          label="Impacto potencial"
          value={money(impact)}
          hint={type || severity ? "na seleção atual" : "soma dos alertas"}
          icon={<CircleDollarSign />}
          tone="yellow"
        />
      </div>

      <div className="grid gap-5 xl:grid-cols-[300px_minmax(0,1fr)]">
        {/* ------------------------------------------------------------ filters */}
        <div className="flex flex-col gap-5">
          <Card title="Por tipo" icon={<Layers />} tone="navy">
            <ul className="space-y-1">
              <li>
                <FilterRow
                  active={!type}
                  onClick={() => setType("")}
                  icon={Bell}
                  tone="navy"
                  label="Todos os alertas"
                  count={summary.total}
                />
              </li>
              {types.map((k) => {
                const m = metaOf(k);
                return (
                  <li key={k}>
                    <FilterRow
                      active={type === k}
                      onClick={() => setType(type === k ? "" : k)}
                      icon={m.icon}
                      tone={m.tone}
                      label={m.label}
                      count={summary.by_type[k] ?? 0}
                    />
                  </li>
                );
              })}
            </ul>
          </Card>
          <Card title="Por severidade" icon={<ShieldAlert />} tone="red">
            <div className="flex flex-wrap gap-2">
              {(["", ...SEVERITIES] as string[]).map((s) => {
                const active = severity === s;
                const count = s ? (summary.by_severity[s] ?? 0) : summary.total;
                return (
                  <button
                    key={s || "all"}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setSeverity(s)}
                    className={clsx(
                      "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-1.5 text-xs font-semibold transition",
                      active
                        ? "bg-gradient-to-r from-[#3483fa] to-[#5b9cff] text-white shadow-[0_8px_18px_-8px_rgba(52,131,250,0.8)]"
                        : "border border-white/90 bg-white/80 text-ink-2 shadow-[0_4px_12px_-8px_rgba(45,50,119,0.4)] hover:bg-white hover:text-ink",
                    )}
                  >
                    {s && (
                      <span
                        className={clsx(
                          "h-2 w-2 rounded-full",
                          SEVERITY_DOT[s],
                          active && "ring-2 ring-white/70",
                        )}
                      />
                    )}
                    {s ? t.severity(s) : "Todas"}
                    <span className={clsx("tabular", active ? "text-white/80" : "text-muted")}>{count}</span>
                  </button>
                );
              })}
            </div>
          </Card>
        </div>

        {/* -------------------------------------------------------------- list */}
        <div className="flex min-w-0 flex-col gap-4">
          {alerts.length === 0 && (
            <div className="card">
              <EmptyState title="Nenhum alerta para esta seleção" icon={<Sparkles />}>
                Ajuste os filtros por tipo ou severidade para ver outras exceções.
              </EmptyState>
            </div>
          )}
          {alerts.map((a) => (
            <AlertCard key={a.id} a={a} />
          ))}
        </div>
      </div>
    </div>
  );
}

function FilterRow({
  active,
  onClick,
  icon: Icon,
  tone,
  label,
  count,
}: {
  active: boolean;
  onClick: () => void;
  icon: LucideIcon;
  tone: Tone;
  label: string;
  count: number;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={clsx(
        "flex w-full items-center gap-3 rounded-2xl px-2.5 py-2 text-left text-sm transition",
        active
          ? "bg-white font-semibold text-ink shadow-[0_8px_20px_-12px_rgba(45,50,119,0.45)]"
          : "text-ink-2 hover:bg-white/70",
      )}
    >
      <span
        className={clsx("flex h-7 w-7 shrink-0 items-center justify-center rounded-lg", TONES[tone].soft)}
      >
        <Icon size={14} />
      </span>
      <span className="min-w-0 flex-1 leading-snug">{label}</span>
      <span
        className={clsx(
          "tabular min-w-7 rounded-full px-2 py-0.5 text-center text-[11px] font-bold",
          active ? TONES[tone].soft : "bg-[#eef1fa] text-muted",
        )}
      >
        {count}
      </span>
    </button>
  );
}

function Section({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={className}>
      <div className="label-xs">{label}</div>
      <div className="mt-1 text-sm leading-relaxed">{children}</div>
    </div>
  );
}

function AlertCard({ a }: { a: Alert }) {
  const m = metaOf(a.type);
  const Icon = m.icon;
  const title = titleOf(a);
  const entity = ENTITY_FIELDS.map((k) => [k, a.entity[k]] as const).filter(([, v]) => !!v);
  // Subtitle: the alert type (when the title is custom) and where it happens.
  const subtitle = [title !== m.label && m.label, a.entity.customer, a.entity.sku]
    .filter(Boolean)
    .join(" · ");
  const deepDive = deepDiveHref(a);
  return (
    <article className="card p-5 transition duration-200 hover:shadow-[0_18px_36px_-16px_rgba(45,50,119,0.3)]">
      <header className="flex flex-wrap items-start gap-4">
        <IconTile icon={<Icon />} tone={m.tone} size="md" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[15px] font-semibold tracking-tight text-ink">{title}</h3>
            <SeverityBadge value={a.severity} />
          </div>
          {subtitle && <div className="mt-0.5 text-xs text-muted">{subtitle}</div>}
        </div>
        <div className={clsx("rounded-2xl bg-gradient-to-br px-4 py-2 text-right", TONES.yellow.surface)}>
          <div className="text-[11px] font-medium text-ink-2">Impacto potencial</div>
          <div className="whitespace-nowrap text-base font-bold tracking-tight text-ink">
            {money(a.potential_impact)}
          </div>
        </div>
      </header>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="space-y-3 rounded-2xl bg-[#f6f8fe] p-4">
          <Section label="Problema">
            <span className="text-ink">{a.issue}</span>
          </Section>
          <Section label="Entidade afetada">
            {entity.length === 0 ? (
              <span className="text-muted">—</span>
            ) : (
              <span className="flex flex-wrap gap-1.5">
                {entity.map(([k, v]) => (
                  <span
                    key={k}
                    title={t.dimension(k === "product" ? "sku" : k)}
                    className="inline-flex items-center gap-1 rounded-full border border-white bg-white px-2.5 py-0.5 text-xs text-ink-2 shadow-[0_2px_6px_-4px_rgba(45,50,119,0.4)]"
                  >
                    <span className="text-muted">{k === "product" ? "Produto" : t.dimension(k)}:</span>
                    <span className="font-medium text-ink">{v}</span>
                  </span>
                ))}
              </span>
            )}
          </Section>
          <Section label="Magnitude">
            <span className="font-semibold text-ink">{a.magnitude}</span>
          </Section>
        </div>
        <div className="space-y-3 rounded-2xl bg-[#f6f8fe] p-4">
          <Section label="Explicação">
            <span className="text-ink-2">{a.explanation}</span>
          </Section>
          <div className={clsx("rounded-xl p-3", TONES[m.tone].soft.split(" ")[0])}>
            <div className="label-xs flex items-center gap-1.5">
              <Search size={12} /> Investigação recomendada
            </div>
            <div className="mt-1 text-sm leading-relaxed text-ink">{a.recommendation}</div>
          </div>
        </div>
      </div>

      <footer className="mt-4 flex flex-wrap items-center gap-2">
        {deepDive && (
          <Link to={deepDive} className={PRIMARY_LINK}>
            <ScanSearch size={13} /> Investigar no deep dive
          </Link>
        )}
        {a.entity.series_id && (
          <Link
            to={ROUTES.workspace(a.entity.series_id)}
            className={deepDive ? SECONDARY_LINK : PRIMARY_LINK}
          >
            Abrir no workspace de forecast <ExternalLink size={12} />
          </Link>
        )}
        <Link to={ROUTES.ia(analystQuestion(a))} className={SECONDARY_LINK}>
          <Sparkles size={13} /> Perguntar ao analista de IA
        </Link>
      </footer>
    </article>
  );
}
