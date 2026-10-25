import { useMutation } from "@tanstack/react-query";
import clsx from "clsx";
import { Bot, Cpu, Database, Lightbulb, Send, ShieldCheck, Sparkles, User, Workflow } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ChartRenderer } from "../charts/ChartRenderer";
import { Signature } from "../components/Layout";
import { Badge, Card, ErrorState, PageHeader } from "../components/ui";
import { useGet } from "../hooks/useApi";
import { useFilters } from "../hooks/useFilters";
import { formatValue } from "../lib/format";
import { api } from "../services/api";
import type { AiResponse } from "../types";

interface Message {
  role: "user" | "assistant";
  text?: string;
  response?: AiResponse;
}

interface AiStatus {
  enabled: boolean;
  available: boolean;
  url: string;
  model: string;
  models: string[];
  reason?: string;
}

const TONES: Record<string, string> = {
  green: "text-emerald-700",
  red: "text-red-700",
  yellow: "text-amber-700",
  blue: "text-blue-700",
  orange: "text-orange-700",
};

export default function AIAnalyst() {
  const { filters } = useFilters();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [lang, setLang] = useState<"en" | "pt">("en");
  const { data: status } = useGet<AiStatus>("/api/ai/status");
  const { data: suggestions } = useGet<string[]>("/api/ai/suggestions", { lang });
  const box = useRef<HTMLDivElement>(null);
  const lastUser = useRef<HTMLDivElement>(null);
  const lastUserIndex = messages.map((m) => m.role).lastIndexOf("user");
  const ask = useMutation({
    mutationFn: (q: string) => api.post<AiResponse>("/api/ai/ask", { question: q, filters }),
    onSuccess: (r) => setMessages((m) => [...m, { role: "assistant", response: r }]),
  });
  // Keep the latest question at the top of the chat so the answer is read from its first line.
  useEffect(() => {
    if (box.current && lastUser.current) {
      box.current.scrollTo({ top: Math.max(0, lastUser.current.offsetTop - 12), behavior: "smooth" });
    }
  }, [messages, ask.isPending]);

  const send = (q: string) => {
    const question = q.trim();
    if (!question || ask.isPending) return;
    setMessages((m) => [...m, { role: "user", text: question }]);
    setInput("");
    ask.mutate(question);
  };

  // Deep link: /app/ai?q=Is%20December%20target%20realistic%3F asks the question on arrival.
  const [params] = useSearchParams();
  const asked = useRef(false);
  const initial = params.get("q");
  const { mutate } = ask;
  useEffect(() => {
    if (!initial || asked.current) return;
    asked.current = true;
    setMessages([{ role: "user", text: initial }]);
    mutate(initial);
  }, [initial, mutate]);

  return (
    <div>
      <PageHeader
        eyebrow="AI Demand Analyst"
        title="Ask your demand plan"
        subtitle="Questions are resolved to governed metrics in the semantic layer, computed by the forecasting, scenario, S&OP and FVA engines, then explained. The LLM never invents numbers."
      />
      <div className="grid gap-5 xl:grid-cols-[1fr_340px]">
        <div className="card flex min-h-[640px] flex-col">
          <div
            ref={box}
            className="relative flex-1 space-y-5 overflow-auto p-5"
            style={{ maxHeight: "calc(100vh - 290px)" }}
          >
            {messages.length === 0 && (
              <div className="flex flex-col items-center py-10 text-center">
                <div className="rounded-2xl bg-navy p-3 text-white">
                  <Sparkles size={24} />
                </div>
                <div className="mt-3 text-lg font-semibold">AI Demand Analyst</div>
                <p className="mt-1 max-w-md text-sm text-muted">
                  Ask about accuracy, bias, drivers, targets, what-if scenarios, budget gaps, models or
                  overrides — in English or Portuguese.
                </p>
              </div>
            )}
            {messages.map((m, i) =>
              m.role === "user" ? (
                <div
                  key={i}
                  ref={i === lastUserIndex ? lastUser : undefined}
                  className="flex justify-end gap-2"
                >
                  <div className="max-w-[75%] rounded-2xl rounded-tr-sm bg-ink px-4 py-2.5 text-sm text-white">
                    {m.text}
                  </div>
                  <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-200">
                    <User size={14} />
                  </div>
                </div>
              ) : (
                <AssistantMessage key={i} r={m.response!} />
              ),
            )}
            {ask.isPending && (
              <div className="flex items-center gap-2 text-sm text-muted">
                <Bot size={16} className="animate-pulse text-brand" /> Querying the engines…
              </div>
            )}
            <ErrorState error={ask.error} />
          </div>
          <div className="border-t border-line p-4">
            <div className="mb-3 flex flex-wrap gap-1.5">
              {(suggestions ?? []).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => send(s)}
                  className="rounded-full border border-line bg-white px-3 py-1 text-xs text-ink-2 transition hover:border-brand/50 hover:text-brand"
                >
                  {s}
                </button>
              ))}
              <button
                type="button"
                className="rounded-full px-2 py-1 text-xs text-muted hover:text-ink"
                onClick={() => setLang(lang === "en" ? "pt" : "en")}
              >
                {lang === "en" ? "Sugestões em PT" : "Suggestions in EN"}
              </button>
            </div>
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                send(input);
              }}
            >
              <input
                className="input"
                placeholder="e.g. Is December target realistic?"
                value={input}
                onChange={(e) => setInput(e.target.value)}
              />
              <button type="submit" className="btn-primary" disabled={ask.isPending || !input.trim()}>
                <Send size={15} /> Ask
              </button>
            </form>
          </div>
        </div>

        <div className="flex flex-col gap-5">
          <Card title="Local AI status">
            <div className="flex items-center gap-2">
              <span
                className={clsx(
                  "h-2.5 w-2.5 rounded-full",
                  status?.available ? "bg-emerald-500" : "bg-amber-500",
                )}
              />
              <span className="text-sm font-semibold">
                {status?.available ? `Ollama · ${status.model}` : "Deterministic mode"}
              </span>
            </div>
            <p className="mt-2 text-xs text-muted">
              {status?.available
                ? "Explanations are written by the local LLM and checked against the computed facts (numeric grounding)."
                : `${status?.reason ?? "Ollama not detected"}. Answers use the rule-based narrative engine — every number is still computed by ForecastLab.`}
            </p>
          </Card>
          <Card title="How an answer is produced">
            <ol className="space-y-2.5 text-sm">
              {[
                { icon: User, t: "User question" },
                { icon: Workflow, t: "Intent extraction (rules, LLM fallback)" },
                { icon: Database, t: "Semantic query → DuckDB / engines" },
                { icon: Cpu, t: "Structured result (metrics, chart, table)" },
                { icon: Bot, t: "LLM explanation (grounded)" },
              ].map(({ icon: Icon, t }, i) => (
                <li key={t} className="flex items-center gap-2.5">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-50 text-[11px] font-semibold text-brand">
                    {i + 1}
                  </span>
                  <Icon size={14} className="text-muted" />
                  {t}
                </li>
              ))}
            </ol>
          </Card>
          <Card title="Scope">
            <p className="text-xs text-muted">Page filters are applied to every question:</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {Object.entries(filters).length === 0 && <Badge>All data</Badge>}
              {Object.entries(filters).map(([k, v]) => (
                <Badge key={k} className="bg-blue-50 text-blue-800">
                  {k}: {v}
                </Badge>
              ))}
            </div>
            <div className="mt-4 border-t border-line pt-3">
              <Signature variant="inline" />
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function AssistantMessage({ r }: { r: AiResponse }) {
  const meta = r.meta;
  return (
    <div className="flex gap-2">
      <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-navy text-white">
        <Bot size={14} />
      </div>
      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-sm border border-line bg-white p-4">
        <p className="text-[14.5px] leading-relaxed text-ink">{r.answer}</p>
        {r.metrics.length > 0 && (
          <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
            {r.metrics.map((m) => (
              <div key={m.label} className="rounded-lg border border-line bg-slate-50/60 px-3 py-2">
                <div className="text-[11px] text-muted">{m.label}</div>
                <div className={clsx("text-base font-semibold", m.tone && TONES[m.tone])}>
                  {formatValue(m.value, m.format)}
                </div>
              </div>
            ))}
          </div>
        )}
        {r.chart && (
          <div className="mt-4 rounded-lg border border-line p-3">
            {r.chart.title && <div className="mb-1 text-xs font-semibold text-ink-2">{r.chart.title}</div>}
            <ChartRenderer spec={r.chart} height={280} />
          </div>
        )}
        {r.table && r.table.rows.length > 0 && (
          <div className="mt-4 max-h-72 overflow-auto rounded-lg border border-line">
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
        )}
        {r.insights.length > 0 && (
          <div className="mt-4">
            <div className="label-xs mb-1.5 flex items-center gap-1">
              <Lightbulb size={12} /> Insights
            </div>
            <ul className="space-y-1 text-sm text-ink-2">
              {r.insights.map((t) => (
                <li key={t}>• {t}</li>
              ))}
            </ul>
          </div>
        )}
        {r.recommendations.length > 0 && (
          <div className="mt-3 rounded-lg bg-blue-50/60 p-3">
            <div className="label-xs mb-1 text-brand">Recommendations</div>
            <ul className="space-y-1 text-sm text-ink">
              {r.recommendations.map((t) => (
                <li key={t}>→ {t}</li>
              ))}
            </ul>
          </div>
        )}
        <details className="mt-3 text-xs text-muted">
          <summary className="cursor-pointer select-none">
            <ShieldCheck size={12} className="mr-1 inline" />
            How this was computed · {meta.engine} · {meta.latency_ms} ms
          </summary>
          <div className="mt-2 space-y-1 rounded-lg bg-slate-50 p-3 font-mono text-[11px]">
            <div>
              intent: {meta.intent?.name ?? "—"} ({meta.intent?.source})
            </div>
            <div>
              entities:{" "}
              {JSON.stringify({
                months: meta.intent?.months,
                filters: meta.intent?.filters,
                levers: meta.intent?.levers,
                dimension: meta.intent?.dimension,
              })}
            </div>
            <div>query: {meta.query}</div>
            <div>
              grounding:{" "}
              {meta.grounding.checked
                ? meta.grounding.passed
                  ? "passed ✓"
                  : `rejected (${meta.grounding.violations?.join(", ")})`
                : "deterministic (no LLM)"}
            </div>
            <div>
              run: {meta.run_id} · dataset: {meta.dataset_version}
            </div>
          </div>
        </details>
      </div>
    </div>
  );
}
