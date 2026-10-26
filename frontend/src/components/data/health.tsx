/**
 * Data-health report of a dataset: quality score, validation issues and their pt-BR texts.
 * Extracted from pages/Data.tsx (spec §3, F6 day 0) so the Entrada stage can reuse it.
 */
import clsx from "clsx";
import {
  Ban,
  CalendarCheck,
  CalendarClock,
  CalendarX,
  CircleCheck,
  CircleDashed,
  CircleMinus,
  CircleSlash,
  Copy,
  History,
  Hourglass,
  Info,
  Layers,
  ListChecks,
  Package,
  Rows3,
  ShieldCheck,
  TriangleAlert,
  Users,
  Zap,
} from "lucide-react";
import type { ReactNode } from "react";

import { SERIES, STATUS, TONES, type Tone } from "../../lib/colors";
import { full, monthLabel } from "../../lib/format";
import { t } from "../../lib/labels";
import type { Issue, ValidationReport } from "../../types";
import { Badge, Card, IconTile, ProgressBar, ProgressRing } from "../ui";

/* ------------------------------------------------------------------ helpers */

export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
export const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

/** Canonical column names -> Portuguese display labels. */
const COLUMN_PT: Record<string, string> = {
  date: "Data",
  region: "Região",
  channel: "Canal",
  customer: "Cliente",
  customer_location: "Localização do cliente",
  customer_potential: "Potencial do cliente",
  sku: "SKU",
  product: "Produto",
  category: "Categoria",
  brand: "Marca",
  units: "Unidades",
  revenue: "Receita",
  price: "Preço",
  promotion: "Promoção",
  distribution: "Distribuição",
  stockout: "Ruptura",
  holiday: "Feriado",
  marketing_investment: "Investimento em marketing",
  merchandising_event: "Merchandising",
};
const colLabel = (c: string) => COLUMN_PT[c] ?? c;
const colLower = (c: string) => (c === "sku" ? "SKU" : colLabel(c).toLowerCase());

const EXAMPLE_KEY: Record<string, string> = { row: "linha", z_score: "z-score", sku: "SKU" };
const exampleKey = (k: string) => EXAMPLE_KEY[k] ?? colLower(k);

/** Numeric columns whose example values are shown with pt-BR number formatting. */
const NUMERIC_KEYS = new Set([
  "units",
  "revenue",
  "price",
  "promotion",
  "distribution",
  "stockout",
  "holiday",
  "marketing_investment",
  "merchandising_event",
  "customer_potential",
  "z_score",
]);
const ISO_MONTH = /^(\d{4})-(\d{2})(?:-\d{2})?(?:[ T]00:00:00)?$/;

/** pt-BR display of one example cell (numbers "12.000" / "5,3", dates "mar/2024"); raw text otherwise. */
function exampleValue(key: string, v: unknown): string {
  if (v == null || v === "") return "—";
  if (key === "row") return String(v);
  if (key === "date") {
    const m = ISO_MONTH.exec(String(v));
    return m && Number(m[2]) >= 1 && Number(m[2]) <= 12 ? monthLabel(`${m[1]}-${m[2]}`) : String(v);
  }
  const n = typeof v === "number" ? v : NUMERIC_KEYS.has(key) ? Number(v) : NaN;
  if (Number.isFinite(n)) return full(n, Number.isInteger(n) ? 0 : key === "z_score" ? 1 : 2);
  return String(v);
}

/** Known English API error messages -> Portuguese (other messages pass through unchanged). */
const ERROR_PT: [RegExp, (m: RegExpExecArray) => string][] = [
  [
    /^Unsupported file type(?: '([^']*)')?\. Use one of: (.+)$/i,
    (m) => `Tipo de arquivo não suportado${m[1] ? ` (${m[1]})` : ""}. Use um destes formatos: ${m[2]}.`,
  ],
  [/^File larger than (\d+) MB$/i, (m) => `O arquivo excede o limite de ${m[1]} MB.`],
  [
    /^Could not read the file/i,
    () =>
      "Não foi possível ler o arquivo. Verifique se ele não está corrompido, protegido por senha ou salvo em um formato diferente da extensão.",
  ],
  [
    /^A forecast run is in progress/i,
    () => "Já existe uma execução de forecast em andamento. Aguarde a conclusão e tente novamente.",
  ],
  [
    /^Dataset has critical validation errors$/i,
    () => "Esta base tem erros críticos de validação e não pode ser ativada.",
  ],
  [/^Dataset not found$/i, () => "Base não encontrada."],
  [
    /^(?:No active dataset|Active dataset not found)$/i,
    () => "Nenhuma base ativa. Carregue um arquivo ou a base de demonstração.",
  ],
  [
    /^(?:Failed to fetch|Load failed|NetworkError when attempting to fetch resource\.?)$/i,
    () => "Não foi possível conectar ao servidor. Verifique se a API do ForecastLab está em execução.",
  ],
  [/^(?:Payload Too Large|Request Entity Too Large)$/i, () => "O arquivo é grande demais para ser enviado."],
  [/^Internal Server Error$/i, () => "Erro interno do servidor. Tente novamente em instantes."],
];
export function ptError(e: Error | null | undefined): Error | null {
  if (!e) return null;
  for (const [re, text] of ERROR_PT) {
    const m = re.exec(e.message);
    if (m) return new Error(text(m));
  }
  return e;
}

/** Numbers inside an API message, accepting pt-BR ("1.234", "0,71") and plain ("1234", "0.71") formats. */
const numbersIn = (s: string) =>
  (s.match(/\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?/g) ?? []).map((x) =>
    Number(/\.\d{3}(?:,|$)/.test(x) || x.includes(",") ? x.replace(/\./g, "").replace(",", ".") : x),
  );

/** Portuguese text for a validation issue, built from its code (falls back to the API message). */
export function issueText(i: Issue): string {
  const found = numbersIn(i.message ?? "");
  const n = i.count || found[0] || 0;
  const N = full(n);
  const list = (Array.isArray(i.examples) ? i.examples : []).filter(
    (x): x is string => typeof x === "string",
  );
  switch (i.code) {
    case "missing_columns":
      return list.length
        ? `${plural(list.length, "Coluna obrigatória ausente", "Colunas obrigatórias ausentes")}: ${list.map(colLabel).join(", ")}`
        : i.message;
    case "empty":
      return "O arquivo não tem linhas de dados.";
    case "invalid_dates":
      return `${N} ${plural(n, "linha com data inválida", "linhas com data inválida")}`;
    case "future_dates":
      return `${N} ${plural(n, "linha com data no futuro", "linhas com data no futuro")}`;
    case "missing_units":
      return `${N} ${plural(n, "linha sem unidades (tratada como 0)", "linhas sem unidades (tratadas como 0)")}`;
    case "negative_units":
      return `${N} ${plural(n, "linha com unidades negativas", "linhas com unidades negativas")} — devoluções devem ser abatidas antes do envio`;
    case "distribution_range":
      return `${N} ${plural(n, "valor de distribuição", "valores de distribuição")} fora do intervalo 0–100`;
    case "duplicated_rows":
      return `${N} ${plural(n, "linha totalmente duplicada (removida)", "linhas totalmente duplicadas (removidas)")}`;
    case "aggregated_to_monthly":
      return `${N} ${plural(n, "linha compartilha", "linhas compartilham")} o mesmo Cliente × SKU × Mês e ${plural(n, "foi agregada", "foram agregadas")}`;
    case "short_history":
      return `${N} ${plural(n, "série", "séries")} com menos de ${found[1] ?? 12} meses de histórico (serão usados modelos para histórico curto)`;
    case "insufficient_history":
      return `São necessários pelo menos ${found[0] ?? 6} meses de histórico (encontrados: ${found[1] ?? "—"}).`;
    case "zero_demand_periods":
      return `${N} ${plural(n, "série-mês", "séries-mês")} com demanda zero (meses ausentes são tratados como zero)`;
    case "outliers":
      return `${N} ${plural(n, "outlier sem explicação", "outliers sem explicação")} (z-score robusto > 5 após remover a sazonalidade; meses com promoção, merchandising ou ruptura são desconsiderados)`;
    case "optional_columns_missing":
      return list.length ? `Colunas opcionais não informadas: ${list.map(colLabel).join(", ")}` : i.message;
  }
  const m = /^(missing|non_numeric|negative)_(.+)$/.exec(i.code);
  if (m) {
    const [, kind, c] = m;
    if (kind === "missing") return `${N} ${plural(n, "linha", "linhas")} sem ${colLower(c)}`;
    if (kind === "non_numeric")
      return `${N} ${plural(n, "valor não numérico", "valores não numéricos")} em ${colLabel(c)}`;
    return `${N} ${plural(n, "valor negativo", "valores negativos")} em ${colLabel(c)}`;
  }
  return i.message;
}

/**
 * Portuguese version of the profiling rule explanation. The engine now writes pt-BR text;
 * these patterns only translate legacy English reasons stored with older dataset versions.
 */
const REASON_RULES: [RegExp, string][] = [
  [
    /^No demand in the last 6 months \(possible delisting\)$/,
    "Sem demanda nos últimos 6 meses (possível deslistagem)",
  ],
  [/^Only (\d+) months of history \(< (\d+)\)$/, "Apenas $1 meses de histórico (< $2)"],
  [/^ADI ([\d.]+) >= ([\d.]+) \((\d+)% zero months\)$/, "ADI $1 ≥ $2 ($3% dos meses sem demanda)"],
  [
    /^Demand tracks numeric distribution \(corr ([-\d.]+), range (\d+) pts\)$/,
    "Demanda acompanha a distribuição numérica (corr. $1, amplitude de $2 p.p.)",
  ],
  [/^Level shift of ([+-]?\d+)% detected at month (\d+)$/, "Mudança de nível de $1% detectada no mês $2"],
  [/^Seasonal strength ([\d.]+) >= ([\d.]+)$/, "Força sazonal $1 ≥ $2"],
  [/^Promotion lift ([+-]?\d+)% \(corr ([-\d.]+)\)$/, "Efeito de promoção de $1% (corr. $2)"],
  [/^Trend strength ([\d.]+), ([+-]?\d+)% per year$/, "Força de tendência $1, $2% ao ano"],
  [/^Residual CV ([\d.]+) >= ([\d.]+)$/, "CV residual $1 ≥ $2"],
  [
    /^Low volatility \(residual CV ([\d.]+)\), no dominant pattern$/,
    "Baixa volatilidade (CV residual $1), sem padrão dominante",
  ],
];
export function reasonPt(s: string | null | undefined): string {
  if (!s) return "—";
  const rule = REASON_RULES.find(([re]) => re.test(s));
  // Only legacy English text uses "." as decimal separator; pt-BR text is returned as is.
  return rule ? s.replace(rule[0], rule[1]).replace(/(\d)\.(\d)/g, "$1,$2") : s;
}

/** Plan origin in Portuguese; the backend now writes pt-BR, these only cover legacy English versions. */
export function planLabel(p: string | null | undefined): string {
  if (!p) return "—";
  if (/^Synthetic/i.test(p)) return "Orçamento anual e metas de vendas sintéticos";
  if (/^Uploaded plan/i.test(p)) return "Plano enviado no arquivo";
  if (/^Derived/i.test(p))
    return "Derivado: orçamento = mesmo mês do ano anterior × 1,05; meta = orçamento × 1,05 (desafio)";
  return p;
}

export const scoreColor = (s: number) =>
  s >= 90 ? STATUS.good : s >= 75 ? SERIES.consensus : s >= 60 ? STATUS.warning : STATUS.critical;
const scoreTone = (s: number): Tone => (s >= 90 ? "green" : s >= 75 ? "teal" : s >= 60 ? "yellow" : "red");
const scoreLabel = (s: number) => (s >= 90 ? "Excelente" : s >= 75 ? "Boa" : s >= 60 ? "Regular" : "Baixa");

export const STATUS_TONE: Record<string, Tone> = { valid: "green", warnings: "yellow", blocked: "red" };

const SEV: Record<Issue["severity"], { tone: Tone; icon: ReactNode; order: number }> = {
  critical: { tone: "red", icon: <Ban />, order: 0 },
  warning: { tone: "orange", icon: <TriangleAlert />, order: 1 },
  info: { tone: "blue", icon: <Info />, order: 2 },
};

/* ------------------------------------------------------------ health report */

interface HealthStat {
  label: string;
  value: string;
  sub?: string;
  icon: ReactNode;
  tone: Tone;
}

interface HistorySummary {
  min_months: number;
  median_months: number;
  max_months: number;
  short_series: number;
}

export function HealthReport({ report, title }: { report: ValidationReport; title: string }) {
  const s = report.summary;
  const q = report.quality;
  const missing = s.missing_values as Record<string, number> | undefined;
  const missingTotal = missing ? Object.values(missing).reduce((a, b) => a + b, 0) : undefined;
  const hist = s.history as HistorySummary | undefined;
  const flag = (n: number | null | undefined, critical = false): Tone =>
    n == null ? "blue" : n === 0 ? "green" : critical ? "red" : "orange";
  const issues = [...report.issues].sort(
    (a, b) => (SEV[a.severity]?.order ?? 3) - (SEV[b.severity]?.order ?? 3),
  );
  const count = (sev: Issue["severity"]) => report.issues.filter((i) => i.severity === sev).length;
  const nCritical = count("critical");
  const nWarning = count("warning");
  const nInfo = count("info");
  const statusTone = STATUS_TONE[report.status] ?? "blue";

  const stats: HealthStat[] = [
    { label: "Linhas", value: full(s.rows), icon: <Rows3 />, tone: "blue" },
    { label: "SKUs", value: full(s.n_skus), icon: <Package />, tone: "blue" },
    { label: "Clientes", value: full(s.n_customers), icon: <Users />, tone: "navy" },
    { label: "Séries", value: full(s.n_series), icon: <Layers />, tone: "navy" },
    { label: "Início", value: monthLabel(s.start_date), icon: <CalendarClock />, tone: "purple" },
    { label: "Fim", value: monthLabel(s.end_date), icon: <CalendarCheck />, tone: "purple" },
    {
      label: "Valores ausentes",
      value: full(missingTotal),
      icon: <CircleDashed />,
      tone: flag(missingTotal),
    },
    {
      label: "Linhas duplicadas",
      value: full(s.duplicated_rows),
      icon: <Copy />,
      tone: flag(s.duplicated_rows),
    },
    {
      label: "Datas inválidas",
      value: full(s.invalid_dates),
      icon: <CalendarX />,
      tone: flag(s.invalid_dates, true),
    },
    {
      label: "Valores negativos",
      value: full(s.negative_values),
      icon: <CircleMinus />,
      tone: flag(s.negative_values),
    },
    {
      label: "Períodos sem demanda",
      value: full(s.zero_demand_periods),
      icon: <CircleSlash />,
      tone: "teal",
    },
    { label: "Outliers", value: full(s.outliers), icon: <Zap />, tone: flag(s.outliers) },
    {
      label: "Histórico",
      value: hist ? `${hist.min_months}–${hist.max_months} meses` : "—",
      sub: hist
        ? `mediana de ${full(hist.median_months, Number.isInteger(hist.median_months) ? 0 : 1)} meses`
        : undefined,
      icon: <History />,
      tone: "teal",
    },
    {
      label: "Séries curtas",
      value: full(hist?.short_series),
      sub: "menos de 12 meses",
      icon: <Hourglass />,
      tone: flag(hist?.short_series),
    },
  ];

  return (
    <Card
      title={title}
      subtitle="Validação automática de estrutura, datas, valores e profundidade histórica"
      icon={<ShieldCheck />}
      tone={statusTone}
      actions={
        <Badge className={clsx("px-3 py-1 text-xs", TONES[statusTone].soft)}>
          {report.status === "valid" ? (
            <CircleCheck size={13} />
          ) : report.status === "blocked" ? (
            <Ban size={13} />
          ) : (
            <TriangleAlert size={13} />
          )}
          {t.datasetStatus(report.status)}
        </Badge>
      }
    >
      {!report.can_forecast && (
        <div className="mb-5 flex items-center gap-3 rounded-2xl border border-red-200 bg-gradient-to-r from-red-50 to-white px-4 py-3 text-sm font-semibold text-red-800">
          <IconTile icon={<Ban />} tone="red" size="sm" />
          Execução do forecast bloqueada. Corrija os erros críticos abaixo e carregue novamente.
        </div>
      )}
      {/* Sized by the card's own width (not the viewport): side by side only when there is room. */}
      <div className="@container">
        <div className="grid gap-6 @[48rem]:grid-cols-[250px_minmax(0,1fr)]">
          <div className="flex flex-col items-center gap-5 rounded-3xl bg-gradient-to-br from-white to-[#eef4ff] p-5 ring-1 ring-[#e7eaf5] @[30rem]:flex-row @[48rem]:flex-col">
            <div className="flex shrink-0 flex-col items-center">
              <div className="label-xs mb-3 text-center">Score de qualidade dos dados</div>
              <ProgressRing value={q.overall / 100} size={148} stroke={13} color={scoreColor(q.overall)}>
                <span className="text-[34px] font-bold leading-none tracking-tight text-ink tabular">
                  {Math.round(q.overall)}
                </span>
                <span className="mt-1 text-[11px] font-medium text-muted">de 100</span>
              </ProgressRing>
              <Badge className={clsx("mt-3", TONES[scoreTone(q.overall)].soft)}>
                Qualidade {scoreLabel(q.overall).toLowerCase()}
              </Badge>
            </div>
            <div className="w-full min-w-0 space-y-3 @[30rem]:flex-1 @[48rem]:flex-none">
              {(
                [
                  ["Completude", q.completeness],
                  ["Consistência", q.consistency],
                  ["Profundidade histórica", q.historical_depth],
                  ["Granularidade", q.granularity],
                ] as const
              ).map(([label, v]) => (
                <div key={label}>
                  <div className="mb-1 flex justify-between gap-2 text-xs">
                    <span className="text-ink-2">{label}</span>
                    <span className="font-semibold tabular text-ink">{full(v, 0)}%</span>
                  </div>
                  <ProgressBar value={v / 100} color={v < 60 ? STATUS.critical : undefined} />
                </div>
              ))}
            </div>
          </div>

          <div className="@container min-w-0">
            <div className="grid grid-cols-1 gap-2.5 @[22rem]:grid-cols-2 @[36rem]:grid-cols-3 @[50rem]:grid-cols-4">
              {stats.map((st) => (
                <div
                  key={st.label}
                  className="flex items-center gap-3 rounded-2xl bg-white/80 px-3.5 py-3 ring-1 ring-[#eceff8]"
                >
                  <span
                    className={clsx(
                      "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl [&>svg]:h-[17px] [&>svg]:w-[17px]",
                      TONES[st.tone].soft,
                    )}
                  >
                    {st.icon}
                  </span>
                  <div className="min-w-0">
                    <div className="text-[11px] leading-tight text-muted">{st.label}</div>
                    <div className="text-sm font-semibold tabular text-ink">{st.value}</div>
                    {st.sub && <div className="text-[11px] leading-tight text-muted">{st.sub}</div>}
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-6">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div className="label-xs flex items-center gap-1.5">
                  <ListChecks size={14} /> Pontos de validação
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {nCritical > 0 && (
                    <Badge className={TONES.red.soft}>
                      {nCritical} {plural(nCritical, "crítico", "críticos")}
                    </Badge>
                  )}
                  {nWarning > 0 && (
                    <Badge className={TONES.orange.soft}>
                      {nWarning} {plural(nWarning, "alerta", "alertas")}
                    </Badge>
                  )}
                  {nInfo > 0 && (
                    <Badge className={TONES.blue.soft}>
                      {nInfo} {plural(nInfo, "informativo", "informativos")}
                    </Badge>
                  )}
                </div>
              </div>
              <ul className="space-y-2.5">
                {issues.length === 0 && (
                  <li className="flex items-center gap-3 rounded-2xl bg-gradient-to-r from-emerald-50 to-white px-4 py-3 text-sm font-medium text-emerald-800 ring-1 ring-emerald-100">
                    <IconTile icon={<CircleCheck />} tone="green" size="sm" />
                    Nenhum problema encontrado. A base está pronta para o forecast.
                  </li>
                )}
                {issues.map((i, idx) => (
                  <IssueItem key={`${i.code}-${idx}`} issue={i} />
                ))}
              </ul>
            </div>

            {Object.keys(report.column_mapping ?? {}).length > 0 && (
              <div className="mt-4 text-[11px] leading-relaxed text-muted">
                <span className="font-semibold text-ink-2">Mapeamento de colunas:</span>{" "}
                {Object.entries(report.column_mapping)
                  .map(([a, b]) => (a === b ? colLabel(b) : `${a} → ${colLabel(b)}`))
                  .join(" · ")}
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

export function IssueItem({ issue }: { issue: Issue }) {
  const sev = SEV[issue.severity] ?? SEV.info;
  const examples = (Array.isArray(issue.examples) ? issue.examples : []).filter(
    (e): e is Record<string, unknown> => !!e && typeof e === "object",
  );
  return (
    <li className="flex gap-3 rounded-2xl border border-[#eceff8] bg-white/85 px-4 py-3">
      <IconTile icon={sev.icon} tone={sev.tone} size="sm" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <span className="min-w-0 text-sm font-medium leading-snug text-ink">{issueText(issue)}</span>
          <Badge className={TONES[sev.tone].soft}>{t.issueSeverity(issue.severity)}</Badge>
        </div>
        {examples.length > 0 && (
          <div className="mt-2 space-y-1 overflow-x-auto rounded-xl bg-[#f6f8fe] px-3 py-2 font-mono text-[11px] text-ink-2">
            {examples.map((e, k) => (
              <div key={k} className="whitespace-nowrap">
                {Object.entries(e)
                  .map(([key, v]) => `${exampleKey(key)}=${exampleValue(key, v)}`)
                  .join("  ·  ")}
              </div>
            ))}
          </div>
        )}
      </div>
    </li>
  );
}
