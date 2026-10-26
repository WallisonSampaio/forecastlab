/**
 * Portuguese display labels for codes returned by the API.
 * Unknown values pass through unchanged (e.g. data already in Portuguese).
 */

const SERIES_TYPE: Record<string, string> = {
  Stable: "Estável",
  Trending: "Crescente",
  Declining: "Em declínio",
  Seasonal: "Sazonal",
  Intermittent: "Intermitente",
  "Promo Driven": "Dirigida por promoção",
  "Distribution Driven": "Dirigida por distribuição",
  "Structural Change": "Mudança estrutural",
  Volatile: "Volátil",
  "Short History": "Histórico curto",
  Inactive: "Inativa",
};

const INTERMITTENCY: Record<string, string> = {
  Smooth: "Suave",
  Intermittent: "Intermitente",
  Lumpy: "Irregular",
  Erratic: "Errática",
};

const CONFIDENCE: Record<string, string> = { High: "Alta", Medium: "Média", Low: "Baixa" };

const BIAS: Record<string, string> = { Under: "Subestimado", Balanced: "Equilibrado", Over: "Superestimado" };

const CLASSIFICATION: Record<string, string> = {
  REALISTIC: "Realista",
  STRETCH: "Desafiadora",
  AGGRESSIVE: "Agressiva",
  UNDERESTIMATED: "Subestimada",
};

const SEVERITY: Record<string, string> = { critical: "Crítico", high: "Alto", medium: "Médio", low: "Baixo" };

const FAMILY: Record<string, string> = {
  Baseline: "Linha de base",
  "Exponential Smoothing": "Suavização exponencial",
  ARIMA: "ARIMA",
  Intermittent: "Demanda intermitente",
  Regression: "Regressão",
  "Machine Learning": "Machine Learning",
};

const MODEL: Record<string, string> = {
  Naive: "Ingênuo",
  "Seasonal Naive": "Ingênuo sazonal",
  "Moving Average": "Média Móvel",
  Regression: "Regressão",
};

const EVENT: Record<string, string> = {
  Promotion: "Promoção",
  Merchandising: "Merchandising",
  "Distribution Gain": "Ganho de distribuição",
  "Distribution Loss": "Perda de distribuição",
  "New Store": "Nova loja",
  "Customer Gain": "Ganho de cliente",
  "Customer Loss": "Perda de cliente",
  Campaign: "Campanha",
  "Price Change": "Mudança de preço",
  "New Product": "Lançamento",
  Delisting: "Deslistagem",
  "Competitor Action": "Ação de concorrente",
};

const PLANNER: Record<string, string> = {
  "Key Account Manager": "Key Account (KAM)",
  "Sales Director": "Diretor de Vendas",
  "Trade Marketing": "Trade Marketing",
  "Demand Planner": "Planejador de Demanda",
  Marketing: "Marketing",
};

const OUTCOME: Record<string, string> = { Improved: "Melhorou", Worsened: "Piorou", Neutral: "Neutro" };
const DIRECTION: Record<string, string> = { Upward: "Para cima", Downward: "Para baixo" };

const SCENARIO_KIND: Record<string, string> = {
  base: "Base",
  conservative: "Conservador",
  aggressive: "Agressivo",
  custom: "Personalizado",
};

const LEVER: Record<string, string> = {
  price: "Preço",
  distribution: "Distribuição",
  promotion: "Promoção",
  merchandising: "Merchandising",
  marketing: "Marketing",
  customer_growth: "Crescimento de clientes",
  market_growth: "Crescimento de mercado",
  Distribution: "Distribuição",
  Price: "Preço",
  Marketing: "Marketing",
  Promotions: "Promoções",
};

const RUN_STATUS: Record<string, string> = {
  completed: "Concluído",
  running: "Em execução",
  failed: "Falhou",
  queued: "Na fila",
};

const DATASET_STATUS: Record<string, string> = {
  valid: "Válido",
  warnings: "Com alertas",
  blocked: "Bloqueado",
};

const ISSUE_SEVERITY: Record<string, string> = { critical: "Crítico", warning: "Atenção", info: "Info" };

const DIMENSION: Record<string, string> = {
  company: "Empresa",
  region: "Região",
  channel: "Canal",
  customer: "Cliente",
  category: "Categoria",
  brand: "Marca",
  sku: "SKU",
  planner: "Planejador",
  event_type: "Tipo de evento",
  direction: "Direção",
  magnitude: "Magnitude",
  series: "Série",
  champion: "Modelo campeão",
  series_type: "Padrão de demanda",
};

const ALERT_TYPE: Record<string, string> = {
  high_error: "Erro de forecast elevado",
  severe_over: "Superestimação severa",
  severe_under: "Subestimação severa",
  target_above_p90: "Meta acima do P90",
  structural_change: "Mudança estrutural no forecast",
  challenger_improving: "Desafiante melhorando",
  opportunity: "Oportunidade comercial",
};

/** Root-cause groups of the forecast error (spec §2.0 IBCS tokens, §4.4). */
const CAUSE_GROUP: Record<string, string> = {
  controllable: "Controlável",
  inherent: "Inerente",
  unexplained: "Sem causa identificada",
};

/** Net direction of a forecast error (`CauseRow.direction`). Both directions are errors. */
const ERROR_DIRECTION: Record<string, string> = {
  over: "Superestimou",
  under: "Subestimou",
  mixed: "Direção mista",
};

/** IBCS scenario notation (spec §2.0). */
const NOTATION: Record<string, string> = {
  AC: "Real",
  PY: "Ano anterior",
  PL: "Orçamento",
  TG: "Meta",
  FC: "Consenso",
};

const make = (map: Record<string, string>) => (v: string | null | undefined) => (v ? (map[v] ?? v) : "—");

export const t = {
  seriesType: make(SERIES_TYPE),
  intermittency: make(INTERMITTENCY),
  confidence: make(CONFIDENCE),
  bias: make(BIAS),
  classification: make(CLASSIFICATION),
  severity: make(SEVERITY),
  family: make(FAMILY),
  model: make(MODEL),
  event: make(EVENT),
  planner: make(PLANNER),
  outcome: make(OUTCOME),
  direction: make(DIRECTION),
  scenarioKind: make(SCENARIO_KIND),
  lever: make(LEVER),
  runStatus: make(RUN_STATUS),
  datasetStatus: make(DATASET_STATUS),
  issueSeverity: make(ISSUE_SEVERITY),
  dimension: make(DIMENSION),
  alertType: make(ALERT_TYPE),
  causeGroup: make(CAUSE_GROUP),
  errorDirection: make(ERROR_DIRECTION),
  notation: make(NOTATION),
};

/** Translate a group key (planner, event type, …) by dimension name. */
export function groupLabel(dim: string, value: string): string {
  if (dim === "planner") return t.planner(value);
  if (dim === "event_type") return t.event(value);
  if (dim === "direction") return t.direction(value);
  return value;
}
