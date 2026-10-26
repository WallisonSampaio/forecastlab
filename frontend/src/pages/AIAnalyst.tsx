import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Bot,
  ChevronDown,
  Crosshair,
  Database,
  Filter,
  Hash,
  Lightbulb,
  MessageCircleQuestion,
  MessageSquare,
  Package,
  Percent,
  RotateCcw,
  Scale,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Table2,
  Target,
  TrendingUp,
  Trophy,
  User,
  UserCog,
  Wallet,
  Workflow,
  X,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation, useSearchParams } from "react-router-dom";

import { ChartRenderer } from "../charts/ChartRenderer";
import { Badge, Card, ErrorState, IconTile, PageHeader } from "../components/ui";
import { useGet } from "../hooks/useApi";
import { useFilters } from "../hooks/useFilters";
import { TONES, type Tone } from "../lib/colors";
import { formatValue, monthLabel, pct, shortMonth } from "../lib/format";
import { t } from "../lib/labels";
import { ApiError, api } from "../services/api";
import type { AiResponse, ChartSpec, Filters, MetricCard } from "../types";

/* ------------------------------------------------------------------ contracts */
/** `narration` block of /api/ai/ask: can the local LLM refine this answer in the background? */
interface Narration {
  available: boolean;
  model: string | null;
  reason: string | null;
}

/** /api/ai/ask response: the deterministic answer, returned at once. */
type AskResponse = AiResponse & {
  understood?: boolean;
  /** The rules did not understand the question but the local LLM can try (route_with_llm). */
  interpretable?: boolean;
  narration?: Narration;
  /** Compact facts (≤ 1.800 chars) sent back to /api/ai/narrate. */
  facts?: Record<string, unknown>;
};

/** /api/ai/narrate response. */
interface NarrateResult {
  status: "ok" | "rejected" | "timeout" | "unavailable" | "cancelled";
  reason?: string | null;
  model?: string | null;
  elapsed_s?: number;
  answer?: string;
  insights?: string[];
  recommendations?: string[];
  grounding?: { checked: boolean; passed?: boolean; violations?: string[] };
}

type NarrationState =
  | { phase: "pending"; model: string; startedAt: number }
  | { phase: "done"; result: NarrateResult }
  | { phase: "error"; reason: string };

interface Message {
  id: number;
  role: "user" | "assistant";
  text?: string;
  response?: AskResponse;
  /** Waiting for the local LLM to interpret a question the rules did not understand. */
  interpreting?: { startedAt: number };
  narration?: NarrationState;
  /** The user toggled back to the computed version of a refined answer. */
  showComputed?: boolean;
}

interface AiStatus {
  enabled: boolean;
  available: boolean;
  url: string;
  model: string | null;
  models: string[];
  reason?: string | null;
  note?: string | null;
  checking?: boolean;
  warmup?: { state: "idle" | "loading" | "ready" | "failed"; elapsed_s: number | null };
}

/* ------------------------------------------------------------------ labels */
const INTENT_LABEL: Record<string, string> = {
  forecast_value: "Previsão de vendas",
  metric_lookup: "Consulta de métrica",
  entity_overview: "Visão da entidade",
  what_if: "Simulação what-if",
  target_feasibility: "Viabilidade da meta",
  fva_overrides: "FVA dos ajustes comerciais",
  best_model: "Melhor modelo",
  bias_ranking: "Ranking de viés",
  worst_accuracy: "Ranking de acurácia",
  budget_gap: "Gap vs orçamento",
  forecast_drivers: "Drivers do forecast",
  risks: "Riscos e alertas",
  model_distribution: "Distribuição de modelos campeões",
  series_types: "Perfil das séries",
  summary: "Resumo executivo",
};

const SOURCE_LABEL: Record<string, string> = {
  rules: "regras",
  llm: "intenção interpretada pela IA local",
};

const DIRECTION_LABEL: Record<string, string> = {
  over: "superestimado",
  under: "subestimado",
  abs: "em módulo",
  best: "melhores",
  worst: "piores",
  up: "para cima",
  down: "para baixo",
};

const ENGINE_LABEL: Record<string, string> = {
  "rule-based NLG": "Narrativa por regras",
  none: "sem motor de cálculo",
};

function engineLabel(engine: string): string {
  if (engine.startsWith("ollama:")) return `IA local · ${engine.slice("ollama:".length)}`;
  return ENGINE_LABEL[engine] ?? engine;
}

/** Backend reasons are pt-BR sentences; drop the final period to embed them in a longer text. */
const clause = (s?: string | null) => (s ?? "IA local não detectada").replace(/\.\s*$/, "");

const seconds = (s: number) => `${Math.max(0, Math.round(s))}s`;

/** Dimension name in running text ("cliente", "região", but "SKU" stays upper case). */
const dimWord = (d: string) => (d === "sku" ? "SKU" : t.dimension(d).toLowerCase());

/* ------------------------------------------- pt-BR display of backend labels */
// The analyst backend may still return a few English labels (table columns, series names,
// model and demand-pattern codes). Known ones are translated for display only.
const TERMS: Record<string, string> = {
  Actual: "Real",
  Actuals: "Real",
  Budget: "Orçamento",
  Target: "Meta",
  Consensus: "Consenso",
  "Consensus Forecast": "Forecast de consenso",
  Statistical: "Estatístico",
  "Statistical Forecast": "Forecast estatístico",
  Scenario: "Cenário",
  Value: "Valor",
  Bias: "Viés",
  Accuracy: "Acurácia",
  Model: "Modelo",
  Series: "Séries",
  Champion: "Campeão",
  Challenger: "Desafiante",
  Rank: "Posição",
  Lever: "Alavanca",
  "Units impact": "Impacto em unidades",
  Month: "Mês",
  Customer: "Cliente",
  Planner: "Planejador",
  Event: "Evento",
  "Adj.": "Ajuste",
  Override: "Com ajuste",
  Alert: "Alerta",
  Entity: "Entidade",
  "Impact (R$)": "Impacto (R$)",
  "Last year": "Ano anterior",
  "Commercial events": "Eventos comerciais",
  Growth: "Crescimento",
  Revenue: "Receita",
  Units: "Unidades",
};
const CODE_LABELS = [t.model, t.seriesType, t.lever, t.event, t.planner, t.dimension];
const MONTH_RE = /^\d{4}-\d{2}(-\d{2})?$/;

/** Exact-match label translation (column headers, series names, categories, codes). */
function ptLabel(v: string): string {
  if (!v) return v;
  if (TERMS[v]) return TERMS[v];
  for (const f of CODE_LABELS) {
    const r = f(v);
    if (r !== v) return r;
  }
  return v;
}

const CODE_WORDS = [
  "Seasonal Naive",
  "Moving Average",
  "Promo Driven",
  "Distribution Driven",
  "Structural Change",
  "Short History",
  "Regression",
  "Stable",
  "Trending",
  "Declining",
  "Seasonal",
  "Intermittent",
  "Volatile",
  "Inactive",
];
const CODE_RE = new RegExp(`\\b(${CODE_WORDS.join("|")})\\b`, "g");
const DIM_RE = /\bpor (event[ _]type|customer|region|channel|category|brand|sku|planner|company)\b/g;

/** Portuguese prose from the backend: fix leftover English terms and codes. */
function ptProse(s: string): string {
  if (!s) return s;
  return s
    .replace(/\bconsensus\b/g, "consenso")
    .replace(/\bConsensus\b/g, "Consenso")
    .replace(DIM_RE, (_, d: string) => `por ${dimWord(d.replace(" ", "_"))}`)
    .replace(CODE_RE, (w) => (t.model(w) !== w ? t.model(w) : t.seriesType(w)));
}

/** Text cell of the answer table: months as "jul/2026", known codes in Portuguese. */
function ptCell(v: unknown, format: string | undefined): unknown {
  if (typeof v !== "string" || (format && format !== "text")) return v;
  return MONTH_RE.test(v) ? monthLabel(v) : ptProse(ptLabel(v));
}

function ptChart(spec: ChartSpec): ChartSpec {
  return {
    ...spec,
    title: spec.title ? ptProse(spec.title) : spec.title,
    x: spec.x?.map((v) => (MONTH_RE.test(v) ? shortMonth(v) : ptLabel(v))),
    series: spec.series?.map((s) => ({ ...s, name: ptLabel(s.name) })),
  };
}

/** Answer as displayed: Portuguese answers get their leftover English labels translated. */
function localize(r: AiResponse): AiResponse {
  if (r.meta.language === "en") return r;
  return {
    ...r,
    answer: ptProse(r.answer),
    insights: r.insights.map(ptProse),
    recommendations: r.recommendations.map(ptProse),
    metrics: r.metrics.map((m) => ({
      ...m,
      label: ptProse(ptLabel(m.label)),
      hint: m.hint ? ptProse(m.hint) : m.hint,
    })),
    chart: r.chart ? ptChart(r.chart) : r.chart,
    table: r.table
      ? {
          ...r.table,
          columns: r.table.columns.map(ptLabel),
          rows: r.table.rows.map((row) => row.map((v, j) => ptCell(v, r.table?.formats?.[j]))),
        }
      : r.table,
  };
}

/** Error shown in the chat when the analyst cannot be reached. */
function askError(e: Error | null): Error | null {
  if (!e) return null;
  const status = e instanceof ApiError ? ` (erro ${e.status})` : "";
  return new Error(
    `Não foi possível obter a resposta do analista${status}. Verifique se a API do ForecastLab está em execução e tente novamente.`,
  );
}

/** Human-readable summary of the entities extracted from the question. */
function entitiesLabel(intent: Record<string, unknown> | null | undefined): string {
  if (!intent) return "—";
  const parts: string[] = [];
  const months = intent.months as string[] | undefined;
  if (months?.length) parts.push(`meses: ${months.map((m) => monthLabel(m)).join(", ")}`);
  const filters = intent.filters as Record<string, string> | undefined;
  Object.entries(filters ?? {}).forEach(([k, v]) => parts.push(`${dimWord(k)}: ${v}`));
  const levers = intent.levers as Record<string, unknown> | unknown[] | undefined;
  if (levers && !Array.isArray(levers)) {
    Object.entries(levers).forEach(([k, v]) =>
      parts.push(
        `alavanca ${t.lever(k).toLowerCase()}${typeof v === "number" ? ` ${pct(Math.abs(v) > 1 ? v / 100 : v, 0, true)}` : ""}`,
      ),
    );
  } else if (Array.isArray(levers) && levers.length) {
    parts.push(
      `alavancas: ${levers.map((l) => (typeof l === "string" ? t.lever(l) : JSON.stringify(l))).join(", ")}`,
    );
  }
  const dim = intent.dimension as string | undefined;
  if (dim) parts.push(`dimensão: ${dimWord(dim)}`);
  const dir = intent.direction as string | undefined;
  if (dir) parts.push(`direção: ${DIRECTION_LABEL[dir] ?? dir}`);
  return parts.length ? parts.join(" · ") : "nenhuma (escopo total)";
}

/* --------------------------------------------------------------- visual maps */
const TONE_ALIASES: Record<string, Tone> = {
  green: "green",
  red: "red",
  yellow: "yellow",
  amber: "yellow",
  blue: "blue",
  orange: "orange",
  navy: "navy",
  purple: "purple",
  pink: "pink",
  teal: "teal",
};

function metricVisual(m: MetricCard): { icon: ReactNode; tone: Tone } {
  const fallback: Record<string, Tone> = {
    currency: "blue",
    units: "navy",
    percent: "purple",
    percent_signed: "teal",
    number: "blue",
  };
  const tone = (m.tone && TONE_ALIASES[m.tone]) || fallback[m.format] || "blue";
  const icon =
    m.format === "currency" ? (
      <Wallet />
    ) : m.format === "units" ? (
      <Package />
    ) : m.format === "percent" ? (
      <Percent />
    ) : m.format === "percent_signed" ? (
      <TrendingUp />
    ) : (
      <Hash />
    );
  return { icon, tone };
}

/** Pick an icon for a suggested question from its wording. */
function suggestionIcon(q: string): ReactNode {
  const s = q.toLowerCase();
  if (/meta|target/.test(s)) return <Target />;
  if (/acur|accura|erro|error/.test(s)) return <Crosshair />;
  if (/superestim|subestim|overforecast|underforecast|vi[eé]s|bias/.test(s)) return <Scale />;
  if (/acontece|happens|what-if|simul|aumentar|increase/.test(s)) return <SlidersHorizontal />;
  if (/ajuste|override/.test(s)) return <UserCog />;
  if (/orçamento|orcamento|budget/.test(s)) return <Wallet />;
  if (/risco|risk|alert/.test(s)) return <AlertTriangle />;
  if (/modelo|model/.test(s)) return <Trophy />;
  if (/cresc|growth|driv|impuls/.test(s)) return <TrendingUp />;
  return <MessageSquare />;
}
const SUGGESTION_TONES: Tone[] = ["blue", "purple", "teal", "orange", "green", "pink", "navy", "yellow"];

/** A fallback answer (intent not understood) returns example questions instead of advice. */
function isQuestionList(r: AiResponse): boolean {
  if (r.recommendations.length === 0) return false;
  return !r.meta.intent || r.recommendations.every((x) => x.trim().endsWith("?"));
}

/** POST with an AbortSignal (background narration / LLM routing can be cancelled). */
async function postJson<T>(path: string, body: unknown, signal: AbortSignal): Promise<T> {
  const res = await fetch(api.url(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return (await res.json()) as T;
}

/** Seconds since `startedAt`, re-rendered every second while mounted. */
function useElapsed(startedAt: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return (now - startedAt) / 1000;
}

/* ====================================================================== page */
export default function AIAnalyst() {
  const { filters, clear } = useFilters();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  // Re-checked quickly while the backend is still probing Ollama or loading the model, then every minute.
  const { data: status, isLoading: firstLoad } = useGet<AiStatus>("/api/ai/status", undefined, {
    refetchInterval: (q) =>
      q.state.data?.checking || q.state.data?.warmup?.state === "loading" ? 3000 : 60000,
  });
  // The backend answers "checking" (not available yet) while its first probe of Ollama is still running.
  const statusLoading = firstLoad || !!status?.checking;
  const { data: suggestions } = useGet<string[]>("/api/ai/suggestions", { lang: "pt" });
  const box = useRef<HTMLDivElement>(null);
  const lastUser = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);
  const narrateCtl = useRef<AbortController | null>(null);
  const routeCtl = useRef<AbortController | null>(null);
  const lastUserIndex = messages.map((m) => m.role).lastIndexOf("user");

  const patch = (id: number, fn: (m: Message) => Message) =>
    setMessages((ms) => ms.map((m) => (m.id === id ? fn(m) : m)));

  /** A new question supersedes the background work (narration, LLM routing) of the previous one. */
  const abortBackground = () => {
    narrateCtl.current?.abort();
    narrateCtl.current = null;
    routeCtl.current?.abort();
    routeCtl.current = null;
  };
  useEffect(() => abortBackground, []);

  /** Background rewrite of a computed answer by the local LLM (the computed one stays on screen). */
  const startNarration = (id: number, question: string, r: AskResponse, scope: Filters) => {
    if (!r.narration?.available) return;
    const ctl = new AbortController();
    narrateCtl.current = ctl;
    const pending: NarrationState = {
      phase: "pending",
      model: r.narration.model ?? "modelo local",
      startedAt: Date.now(),
    };
    patch(id, (m) => ({ ...m, narration: pending }));
    postJson<NarrateResult>(
      "/api/ai/narrate",
      {
        question,
        lang: r.meta.language,
        filters: scope,
        answer: {
          answer: r.answer,
          insights: r.insights,
          recommendations: r.recommendations,
          facts: r.facts ?? {},
        },
      },
      ctl.signal,
    )
      .then((result) => patch(id, (m) => ({ ...m, narration: { phase: "done", result } })))
      .catch(() =>
        patch(id, (m) => ({
          ...m,
          narration: ctl.signal.aborted
            ? { phase: "done", result: { status: "cancelled" } }
            : {
                phase: "error",
                reason: "Não foi possível refinar com a IA local; mantida a versão calculada.",
              },
        })),
      )
      .finally(() => {
        if (narrateCtl.current === ctl) narrateCtl.current = null;
      });
  };

  /** Deterministic answer received: show it now; refine or interpret it in the background. */
  const onAnswer = (question: string, r: AskResponse, scope: Filters) => {
    const id = nextId.current++;
    if (r.understood === false && r.interpretable) {
      const interpreting = { startedAt: Date.now() };
      setMessages((ms) => [...ms, { id, role: "assistant", response: r, interpreting }]);
      const ctl = new AbortController();
      routeCtl.current = ctl;
      postJson<AskResponse>("/api/ai/ask", { question, filters: scope, route_with_llm: true }, ctl.signal)
        .then((routed) => {
          patch(id, (m) => ({ ...m, response: routed, interpreting: undefined }));
          if (!ctl.signal.aborted) startNarration(id, question, routed, scope);
        })
        // Cancelled or failed: the help answer (example questions) stays.
        .catch(() => patch(id, (m) => ({ ...m, interpreting: undefined })))
        .finally(() => {
          if (routeCtl.current === ctl) routeCtl.current = null;
        });
      return;
    }
    setMessages((ms) => [...ms, { id, role: "assistant", response: r }]);
    startNarration(id, question, r, scope);
  };

  const ask = useMutation({
    mutationFn: (q: string) => api.post<AskResponse>("/api/ai/ask", { question: q, filters }),
    onSuccess: (r, q) => onAnswer(q, r, filters),
  });
  const { mutate, isPending } = ask;

  // Keep the latest question at the top of the chat so the answer is read from its first line.
  useEffect(() => {
    if (box.current && lastUser.current) {
      box.current.scrollTo?.({ top: Math.max(0, lastUser.current.offsetTop - 16), behavior: "smooth" });
    }
  }, [messages.length, isPending]);

  const send = (q: string) => {
    const question = q.trim();
    if (!question || isPending) return;
    abortBackground();
    setMessages((m) => [...m, { id: nextId.current++, role: "user", text: question }]);
    setInput("");
    mutate(question);
  };

  // Deep link: /app/ai?q=... asks the question on arrival AND every time the top-bar search
  // navigates here again (even while already on this page, even with the same question).
  const [params] = useSearchParams();
  const location = useLocation();
  const q = params.get("q")?.trim() || null;
  const lastAsked = useRef<string | null>(null);
  useEffect(() => {
    if (!q || isPending) return;
    const token = `${location.key}|${q}`;
    if (lastAsked.current === token) return;
    lastAsked.current = token;
    abortBackground();
    setMessages((m) => [...m, { id: nextId.current++, role: "user", text: q }]);
    mutate(q);
  }, [q, location.key, isPending, mutate]);

  const reset = () => {
    abortBackground();
    setMessages([]);
    ask.reset();
  };

  const filterEntries = Object.entries(filters).filter(([, v]) => !!v);
  const online = !!status?.available;
  const loadingModel = online && status?.warmup?.state === "loading";
  const statusText = statusLoading
    ? "Verificando a IA local…"
    : online
      ? `IA local conectada · ${status?.model}`
      : "Modo determinístico · respostas por regras";

  return (
    <div>
      <style>{SHIMMER_CSS}</style>
      <PageHeader
        eyebrow="Analista de IA"
        icon={<Sparkles />}
        title="Converse com o seu plano de demanda"
        subtitle="Cada pergunta é traduzida em métricas governadas da camada semântica e calculada na hora pelos motores de forecast, cenários, S&OP e FVA. A IA local apenas refina o texto em segundo plano, e cada número é conferido com os fatos calculados."
      />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        {/* ------------------------------------------------------------ chat */}
        <section className="card flex min-h-[640px] min-w-0 flex-col overflow-hidden">
          <header className="flex items-center gap-3 border-b border-line/70 px-5 py-4">
            <IconTile icon={<Sparkles />} tone="navy" size="md" />
            <div className="min-w-0">
              <div className="text-[15px] font-semibold text-ink">Analista de demanda</div>
              <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                <span
                  className={clsx(
                    "h-2 w-2 shrink-0 rounded-full",
                    statusLoading ? "bg-slate-300" : online ? "bg-emerald-500" : "bg-amber-400",
                  )}
                />
                {statusText}
              </div>
            </div>
            <button
              type="button"
              className="btn-ghost ml-auto px-3 py-2 text-xs"
              onClick={reset}
              disabled={messages.length === 0 || isPending}
            >
              <RotateCcw size={14} /> Nova conversa
            </button>
          </header>

          <div
            ref={box}
            className="relative flex-1 space-y-6 overflow-auto px-5 py-6"
            style={{ maxHeight: "calc(100vh - 330px)" }}
          >
            {messages.length === 0 && (
              <div className="mx-auto flex max-w-2xl flex-col items-center py-4 text-center">
                <div className="relative">
                  <div className="absolute inset-0 -z-10 scale-150 rounded-full bg-[#3483fa]/15 blur-2xl" />
                  <IconTile icon={<Sparkles />} tone="navy" size="lg" />
                </div>
                <h2 className="mt-4 text-xl font-bold tracking-tight text-ink">
                  Olá! Sou o seu analista de demanda
                </h2>
                <p className="mt-1.5 max-w-lg text-sm leading-relaxed text-muted">
                  Pergunte em linguagem natural sobre acurácia, viés, drivers, metas, cenários what-if, gaps
                  de orçamento, modelos ou ajustes comerciais — de um cliente, SKU, região ou mês específico.
                </p>
                <div className="mt-6 grid w-full gap-3 sm:grid-cols-2">
                  {(suggestions ?? []).slice(0, 6).map((s, i) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => send(s)}
                      className="group flex items-center gap-3 rounded-2xl border border-white/90 bg-white/80 p-3.5 text-left shadow-[0_8px_22px_-16px_rgba(45,50,119,0.45)] transition duration-200 hover:-translate-y-0.5 hover:bg-white hover:shadow-[0_16px_30px_-16px_rgba(45,50,119,0.4)]"
                    >
                      <IconTile
                        icon={suggestionIcon(s)}
                        tone={SUGGESTION_TONES[i % SUGGESTION_TONES.length]}
                        size="sm"
                      />
                      <span className="text-sm font-medium leading-snug text-ink-2 group-hover:text-ink">
                        {s}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m, i) =>
              m.role === "user" ? (
                <div
                  key={m.id}
                  ref={i === lastUserIndex ? lastUser : undefined}
                  className="flex justify-end gap-3"
                >
                  <div className="max-w-[78%] break-words rounded-3xl rounded-tr-lg bg-gradient-to-br from-[#3483fa] to-[#5b9cff] px-4 py-3 text-sm leading-relaxed text-white shadow-[0_12px_26px_-12px_rgba(52,131,250,0.85)]">
                    {m.text}
                  </div>
                  <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/90 bg-white text-brand shadow-[0_6px_14px_-8px_rgba(45,50,119,0.4)]">
                    <User size={16} />
                  </div>
                </div>
              ) : (
                <AssistantMessage
                  key={m.id}
                  m={m}
                  onAsk={send}
                  onToggle={() => patch(m.id, (x) => ({ ...x, showComputed: !x.showComputed }))}
                />
              ),
            )}
            {isPending && (
              <div className="flex gap-3">
                <IconTile icon={<Bot />} tone="navy" size="sm" className="animate-pulse" />
                <div className="flex items-center gap-3 rounded-3xl rounded-tl-lg border border-white/90 bg-white/90 px-4 py-3 text-sm text-muted shadow-[0_14px_34px_-18px_rgba(45,50,119,0.35)]">
                  <span className="flex gap-1" aria-hidden>
                    {[0, 150, 300].map((d) => (
                      <span
                        key={d}
                        className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand"
                        style={{ animationDelay: `${d}ms` }}
                      />
                    ))}
                  </span>
                  Consultando os motores de cálculo…
                </div>
              </div>
            )}
            <ErrorState error={askError(ask.error)} />
          </div>

          <footer className="border-t border-line/70 bg-white/50 px-5 pb-4 pt-3">
            {messages.length > 0 && (suggestions?.length ?? 0) > 0 && (
              <div className="-mx-1 mb-3 flex gap-2 overflow-x-auto px-1 pb-1">
                {(suggestions ?? []).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => send(s)}
                    disabled={isPending}
                    className="shrink-0 whitespace-nowrap rounded-full border border-white/90 bg-white/90 px-3.5 py-1.5 text-xs font-medium text-ink-2 shadow-[0_4px_12px_-8px_rgba(45,50,119,0.45)] transition hover:text-brand disabled:opacity-50"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
            <form
              className="flex items-center gap-2 rounded-2xl border border-line bg-white p-1.5 pl-4 shadow-[0_10px_26px_-18px_rgba(45,50,119,0.5)] transition focus-within:border-brand/50 focus-within:ring-4 focus-within:ring-brand/10"
              onSubmit={(e) => {
                e.preventDefault();
                send(input);
              }}
            >
              <Sparkles size={17} className="shrink-0 text-brand" />
              <input
                className="min-w-0 flex-1 bg-transparent py-2 text-sm text-ink outline-none placeholder:text-muted"
                placeholder="Pergunte qualquer coisa sobre o plano… ex.: a meta de dezembro como está?"
                aria-label="Pergunta para o analista de IA"
                value={input}
                onChange={(e) => setInput(e.target.value)}
              />
              <button type="submit" className="btn-primary px-4" disabled={isPending || !input.trim()}>
                <Send size={15} /> Perguntar
              </button>
            </form>
            <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[11.5px] text-muted">
              <span className="inline-flex items-center gap-1.5">
                <ShieldCheck size={13} className="shrink-0 text-emerald-600" />
                Os números são calculados pelo ForecastLab; a IA local apenas reescreve o texto.
              </span>
            </div>
          </footer>
        </section>

        {/* ------------------------------------------------------- right rail */}
        <aside className="flex min-w-0 flex-col gap-5">
          <Card title="Status da IA local" icon={<Bot />} tone={online ? "green" : "yellow"}>
            <div
              className={clsx(
                "flex items-center gap-2.5 rounded-2xl px-3.5 py-2.5",
                statusLoading ? "bg-slate-100 text-ink-2" : online ? TONES.green.soft : TONES.yellow.soft,
              )}
            >
              <span className="relative flex h-2.5 w-2.5 shrink-0">
                {online && (
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
                )}
                <span
                  className={clsx(
                    "relative inline-flex h-2.5 w-2.5 rounded-full",
                    statusLoading ? "bg-slate-300" : online ? "bg-emerald-500" : "bg-amber-500",
                  )}
                />
              </span>
              <span className="min-w-0 break-words text-sm font-semibold">
                {statusLoading
                  ? "Verificando…"
                  : online
                    ? `IA local conectada · ${status?.model}`
                    : "Modo determinístico"}
              </span>
            </div>
            {!statusLoading && (
              <p className="mt-3 text-xs leading-relaxed text-muted">
                {online
                  ? "As respostas aparecem na hora, calculadas pelo ForecastLab. Em seguida a IA local reescreve a explicação em segundo plano, e o texto só é trocado se todos os números conferirem com os fatos calculados."
                  : `${clause(status?.reason)}. As respostas usam o motor narrativo por regras — todos os números continuam sendo calculados pelo ForecastLab.`}
              </p>
            )}
            {loadingModel && (
              <p className="mt-2 text-xs leading-relaxed text-muted">
                Carregando o modelo na memória; o primeiro refinamento pode demorar um pouco mais.
              </p>
            )}
            {online && status?.note && (
              <p className="mt-2 text-xs leading-relaxed text-muted">{status.note}</p>
            )}
          </Card>

          <Card title="Como uma resposta é produzida" icon={<Workflow />} tone="purple">
            <ol className="relative space-y-3.5">
              <span
                aria-hidden
                className="absolute bottom-5 left-[17px] top-5 w-px bg-gradient-to-b from-[#d9def0] to-[#eef0f7]"
              />
              {(
                [
                  { icon: <MessageSquare />, tone: "blue", text: "Sua pergunta em linguagem natural" },
                  {
                    icon: <Workflow />,
                    tone: "purple",
                    text: "Intenção e entidades por regras (a IA local só interpreta o que as regras não reconhecem)",
                  },
                  {
                    icon: <Database />,
                    tone: "teal",
                    text: "Consulta semântica → DuckDB e motores de cálculo",
                  },
                  {
                    icon: <BarChart3 />,
                    tone: "orange",
                    text: "Resposta na hora: métricas, gráfico, tabela e texto calculados",
                  },
                  {
                    icon: <ShieldCheck />,
                    tone: "green",
                    text: "Refinamento opcional do texto pela IA local, com números verificados",
                  },
                ] as { icon: ReactNode; tone: Tone; text: string }[]
              ).map((s, i) => (
                <li key={s.text} className="relative flex items-center gap-3">
                  <IconTile icon={s.icon} tone={s.tone} size="sm" />
                  <div className="min-w-0">
                    <div className="text-[10.5px] font-bold uppercase tracking-[0.08em] text-muted">
                      Etapa {i + 1}
                    </div>
                    <div className="text-[13px] font-medium leading-snug text-ink">{s.text}</div>
                  </div>
                </li>
              ))}
            </ol>
          </Card>

          <Card
            title="Escopo"
            subtitle="Os filtros da página valem para todas as perguntas"
            icon={<Filter />}
            tone="teal"
            actions={
              filterEntries.length > 0 ? (
                <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={clear}>
                  <X size={13} /> Limpar
                </button>
              ) : undefined
            }
          >
            <div className="flex flex-wrap gap-1.5">
              {filterEntries.length === 0 && <Badge className={TONES.blue.soft}>Todos os dados</Badge>}
              {filterEntries.map(([k, v]) => (
                <Badge key={k} className={TONES.blue.soft}>
                  {t.dimension(k)}: {v}
                </Badge>
              ))}
            </div>
          </Card>
        </aside>
      </div>
    </div>
  );
}

/* Subtle moving highlight for the "working in the background" lines (reduced motion: static). */
const SHIMMER_CSS = `
@keyframes fl-ai-shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
.fl-ai-shimmer {
  background: linear-gradient(90deg, #8a90ad 0%, #8a90ad 40%, #3483fa 50%, #8a90ad 60%, #8a90ad 100%);
  background-size: 200% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: fl-ai-shimmer 2.4s linear infinite;
}
@media (prefers-reduced-motion: reduce) { .fl-ai-shimmer { animation: none; color: #8a90ad; } }
`;

/** "Working in the background" line with a live seconds counter (announced once, not every second). */
function BackgroundLine({ text, startedAt }: { text: string; startedAt: number }) {
  const elapsed = useElapsed(startedAt);
  return (
    <div className="flex items-center gap-2 text-[12.5px] font-medium" role="status" aria-live="polite">
      <Sparkles size={14} className="shrink-0 animate-pulse text-brand" aria-hidden />
      <span className="fl-ai-shimmer">
        {text} <span aria-hidden>{seconds(elapsed)}</span>
      </span>
    </div>
  );
}

/** Narration outcome under the answer: refining, refined (with toggle) or a muted note. */
function NarrationStatus({
  n,
  showComputed,
  onToggle,
}: {
  n: NarrationState;
  showComputed: boolean;
  onToggle: () => void;
}) {
  if (n.phase === "pending") {
    return (
      <BackgroundLine text={`Refinando a explicação com a IA local (${n.model})…`} startedAt={n.startedAt} />
    );
  }
  if (n.phase === "error") return <p className="text-[12px] leading-relaxed text-muted">{n.reason}</p>;
  const r = n.result;
  if (r.status === "cancelled") return null;
  if (r.status !== "ok") {
    return (
      <p className="text-[12px] leading-relaxed text-muted">{r.reason ?? "Mantida a versão calculada."}</p>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span
        className={clsx(
          "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11.5px] font-semibold",
          showComputed ? "bg-slate-100 text-ink-2" : TONES.green.soft,
        )}
      >
        {showComputed ? (
          <>
            <BarChart3 size={13} className="shrink-0" /> Versão calculada pelo ForecastLab
          </>
        ) : (
          <>
            <Sparkles size={13} className="shrink-0" /> Refinado pela IA local · números verificados ✓
          </>
        )}
      </span>
      <button
        type="button"
        onClick={onToggle}
        className="rounded-full px-2 py-1 text-[11.5px] font-medium text-brand transition hover:bg-[#eaf2ff]"
      >
        {showComputed ? "Ver versão refinada" : "Ver versão calculada"}
      </button>
    </div>
  );
}

/* ========================================================= assistant answer */
function AssistantMessage({
  m,
  onAsk,
  onToggle,
}: {
  m: Message;
  onAsk: (q: string) => void;
  onToggle: () => void;
}) {
  const raw = m.response!;
  const narr = m.narration;
  const refined = narr?.phase === "done" && narr.result.status === "ok" ? narr.result : null;
  const showRefined = !!refined && !m.showComputed;
  const r = localize(
    showRefined
      ? {
          ...raw,
          answer: refined.answer ?? raw.answer,
          insights: refined.insights ?? raw.insights,
          recommendations: refined.recommendations ?? raw.recommendations,
        }
      : raw,
  );
  const meta = r.meta;
  const intent = meta.intent as Record<string, unknown> | null;
  const intentName = (intent?.name as string | undefined) ?? null;
  const intentSource = (intent?.source as string | undefined) ?? null;
  const routing = (meta as { routing?: { model?: string | null; elapsed_s?: number } | null }).routing;
  const questions = isQuestionList(r);
  const rejected =
    narr?.phase === "done" && narr.result.status === "rejected" ? narr.result.grounding : undefined;

  if (m.interpreting) {
    return (
      <div className="flex gap-3">
        <IconTile icon={<Bot />} tone="navy" size="sm" className="mt-0.5" />
        <div className="min-w-0 flex-1 rounded-3xl rounded-tl-lg border border-white/90 bg-white/90 px-5 py-4 shadow-[0_14px_34px_-18px_rgba(45,50,119,0.35)]">
          <BackgroundLine
            text="Interpretando sua pergunta com a IA local…"
            startedAt={m.interpreting.startedAt}
          />
          <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
            As regras não reconheceram a pergunta; a IA local escolhe a análise e o ForecastLab calcula os
            números.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <IconTile icon={<Bot />} tone="navy" size="sm" className="mt-0.5" />
      <div className="min-w-0 flex-1 rounded-3xl rounded-tl-lg border border-white/90 bg-white/90 p-5 shadow-[0_14px_34px_-18px_rgba(45,50,119,0.35)] backdrop-blur">
        <p className="whitespace-pre-line break-words text-[15px] leading-relaxed text-ink">{r.answer}</p>
        {narr && (
          <div className="mt-2.5">
            <NarrationStatus n={narr} showComputed={!!m.showComputed} onToggle={onToggle} />
          </div>
        )}

        {r.metrics.length > 0 && (
          <div className="mt-5 grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
            {r.metrics.map((mc) => {
              const v = metricVisual(mc);
              return (
                <div
                  key={mc.label}
                  className={clsx(
                    "flex min-w-0 items-center gap-3 rounded-2xl border border-white/90 bg-gradient-to-br px-3.5 py-3 shadow-[0_6px_18px_-14px_rgba(45,50,119,0.45)]",
                    TONES[v.tone].surface,
                  )}
                >
                  <IconTile icon={v.icon} tone={v.tone} size="sm" />
                  <div className="min-w-0">
                    <div className="break-words text-[11.5px] font-medium leading-snug text-ink-2">
                      {mc.label}
                    </div>
                    <div className="whitespace-nowrap text-lg font-bold leading-tight tracking-tight text-ink">
                      {formatValue(mc.value, mc.format)}
                    </div>
                    {mc.hint && <div className="mt-0.5 text-[11px] leading-snug text-muted">{mc.hint}</div>}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {r.chart && (
          <div className="mt-5 rounded-2xl border border-line/80 bg-white/80 p-4">
            {r.chart.title && (
              <div className="mb-2 flex items-center gap-2 text-[13px] font-semibold text-ink">
                <BarChart3 size={15} className="shrink-0 text-brand" />
                {r.chart.title}
              </div>
            )}
            <ChartRenderer spec={r.chart} height={280} />
          </div>
        )}

        {r.table && r.table.rows.length > 0 && (
          <div className="mt-5 overflow-hidden rounded-2xl border border-line/80 bg-white/80">
            <div className="flex items-center gap-2 border-b border-line/70 px-4 py-2.5 text-[12px] font-semibold text-ink-2">
              <Table2 size={14} className="text-brand" /> Detalhamento
            </div>
            <div className="max-h-72 overflow-auto">
              <table className="table-base tabular text-xs">
                <thead>
                  <tr>
                    {r.table.columns.map((c) => (
                      <th key={c}>{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {r.table.rows.map((row, i) => (
                    <tr key={i}>
                      {row.map((v, j) => (
                        <td key={j} className={typeof v === "number" ? "text-right" : ""}>
                          {formatValue(v, r.table?.formats?.[j])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {r.insights.length > 0 && (
          <div className="mt-5">
            <div className="mb-2 flex items-center gap-2">
              <span
                className={clsx("flex h-6 w-6 items-center justify-center rounded-lg", TONES.yellow.soft)}
              >
                <Lightbulb size={13} />
              </span>
              <span className="text-[12px] font-bold uppercase tracking-[0.08em] text-ink-2">Leituras</span>
            </div>
            <ul className="space-y-1.5">
              {r.insights.map((x) => (
                <li key={x} className="flex gap-2.5 text-sm leading-relaxed text-ink-2">
                  <span className="mt-[9px] h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
                  <span className="min-w-0 break-words">{x}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {r.recommendations.length > 0 &&
          (questions ? (
            <div className="mt-5 rounded-2xl bg-gradient-to-br from-[#eaf2ff] to-[#f1edff] p-4">
              <div className="mb-2.5 flex items-center gap-1.5 text-[12px] font-bold uppercase tracking-[0.08em] text-brand">
                <MessageCircleQuestion size={14} /> Experimente perguntar
              </div>
              <div className="flex flex-wrap gap-2">
                {r.recommendations.map((x) => (
                  <button
                    key={x}
                    type="button"
                    onClick={() => onAsk(x)}
                    className="rounded-full border border-white bg-white/90 px-3.5 py-1.5 text-left text-xs font-medium text-ink-2 shadow-[0_4px_12px_-8px_rgba(45,50,119,0.45)] transition hover:-translate-y-px hover:text-brand"
                  >
                    {x}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mt-5 rounded-2xl bg-gradient-to-br from-[#eaf2ff] to-[#f1edff] p-4">
              <div className="mb-2 flex items-center gap-1.5 text-[12px] font-bold uppercase tracking-[0.08em] text-brand">
                <Target size={14} /> Recomendações
              </div>
              <ul className="space-y-1.5">
                {r.recommendations.map((x) => (
                  <li key={x} className="flex gap-2 text-sm leading-relaxed text-ink">
                    <ArrowRight size={14} className="mt-[3px] shrink-0 text-brand" />
                    <span className="min-w-0 break-words">{x}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}

        <details className="group mt-4">
          <summary className="inline-flex cursor-pointer select-none list-none flex-wrap items-center gap-1.5 rounded-full bg-[#f3f5fc] px-3 py-1.5 text-[11.5px] font-medium text-ink-2 transition hover:bg-[#eaeefa] hover:text-ink [&::-webkit-details-marker]:hidden">
            <ShieldCheck size={13} className="shrink-0 text-emerald-600" />
            Como esta resposta foi calculada
            <span className="text-muted">
              · {engineLabel(meta.engine)} · {meta.latency_ms} ms
            </span>
            <ChevronDown size={13} className="transition group-open:rotate-180" />
          </summary>
          <dl className="mt-3 grid gap-x-4 gap-y-2 rounded-2xl border border-line/70 bg-[#f7f8fe] p-4 text-xs sm:grid-cols-[120px_minmax(0,1fr)]">
            <dt className="font-semibold text-muted">Intenção</dt>
            <dd className="text-ink">
              {intentName ? (INTENT_LABEL[intentName] ?? intentName) : "não identificada"}
              {intentName && (
                <span className="ml-1 font-mono text-[11px] text-muted">
                  ({intentName}
                  {intentSource ? ` · ${SOURCE_LABEL[intentSource] ?? intentSource}` : ""})
                </span>
              )}
              {intentSource === "llm" && routing?.model && (
                <span className="mt-0.5 block text-[11px] text-muted">
                  Interpretação pela IA local ({routing.model}
                  {typeof routing.elapsed_s === "number"
                    ? ` · ${routing.elapsed_s.toLocaleString("pt-BR")} s`
                    : ""}
                  ), validada contra as intenções e entidades conhecidas.
                </span>
              )}
            </dd>
            <dt className="font-semibold text-muted">Entidades</dt>
            <dd className="text-ink">{entitiesLabel(intent)}</dd>
            <dt className="font-semibold text-muted">Consulta</dt>
            <dd className="break-all font-mono text-[11px] text-ink-2">{meta.query ?? "—"}</dd>
            <dt className="font-semibold text-muted">Conferência</dt>
            <dd>
              {showRefined ? (
                <Badge className={TONES.green.soft}>números verificados ✓</Badge>
              ) : rejected?.checked ? (
                <span className="inline-flex flex-wrap items-center gap-1.5">
                  <Badge className={TONES.red.soft}>texto da IA local recusado</Badge>
                  {(rejected.violations?.length ?? 0) > 0 && (
                    <span className="break-words font-mono text-[11px] text-muted">
                      trechos recusados: {rejected.violations?.join(" · ")}
                    </span>
                  )}
                </span>
              ) : (
                <Badge className="bg-slate-100 text-ink-2">texto calculado (sem IA local)</Badge>
              )}
            </dd>
            <dt className="font-semibold text-muted">Motor</dt>
            <dd className="text-ink">
              {engineLabel(meta.engine)} · {meta.latency_ms} ms
              {refined && (
                <span className="block text-[11px] text-muted">
                  Texto refinado pela IA local ({refined.model}
                  {typeof refined.elapsed_s === "number"
                    ? ` · ${refined.elapsed_s.toLocaleString("pt-BR")} s`
                    : ""}
                  ){m.showComputed ? " — exibindo a versão calculada" : ""}
                </span>
              )}
            </dd>
            <dt className="font-semibold text-muted">Execução</dt>
            <dd className="font-mono text-[11px] text-ink-2">{meta.run_id ?? "—"}</dd>
            <dt className="font-semibold text-muted">Base</dt>
            <dd className="font-mono text-[11px] text-ink-2">{meta.dataset_version || "—"}</dd>
          </dl>
        </details>
      </div>
    </div>
  );
}
