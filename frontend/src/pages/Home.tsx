import {
  ArrowRight,
  Bot,
  BrainCircuit,
  CheckCircle2,
  Database,
  FileSpreadsheet,
  Gauge,
  Linkedin,
  LineChart,
  ShieldCheck,
  SplitSquareHorizontal,
  Target,
} from "lucide-react";
import { Link } from "react-router-dom";

import { ClientLogo, Logo } from "../components/Layout";
import { useGet } from "../hooks/useApi";
import { BRAND } from "../lib/branding";
import { pct } from "../lib/format";

const PILLARS = [
  {
    icon: LineChart,
    title: "Forecast Accuracy",
    text: "15 statistical & ML models compete per series in a rolling-origin backtest.",
  },
  {
    icon: SplitSquareHorizontal,
    title: "Scenario Planning",
    text: "What-if engine with estimated price, distribution and promo sensitivities.",
  },
  {
    icon: Target,
    title: "S&OP",
    text: "Consensus vs budget vs target, risk & opportunity, target feasibility.",
  },
  {
    icon: Bot,
    title: "AI Analytics",
    text: "Local LLM explains results — every number comes from the engines.",
  },
];

const STORY = [
  "Raw Historical Data",
  "Data Quality",
  "Statistical Modeling",
  "Model Competition",
  "Forecast",
  "Business Inputs",
  "Scenario Planning",
  "S&OP",
  "Decision Intelligence",
  "AI Explanation",
];

interface Overview {
  has_run: boolean;
  n_series: number;
  kpis?: { accuracy: number | null };
}

export default function Home() {
  const { data: ov } = useGet<Overview>("/api/overview", undefined, { retry: false });
  const { data: meta } = useGet<{ models: unknown[] }>("/api/meta", undefined, { retry: false });
  return (
    <div className="min-h-full bg-navy text-white">
      <div className="relative overflow-hidden">
        <div
          className="pointer-events-none absolute inset-0 opacity-70"
          style={{
            background:
              "radial-gradient(900px 480px at 15% -10%, rgba(255,230,0,0.20), transparent 60%), radial-gradient(700px 420px at 95% 10%, rgba(52,131,250,0.45), transparent 60%)",
          }}
        />
        <header className="relative mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
          <span className="flex items-center gap-3">
            <Logo dark size={34} />
            <ClientLogo variant="inline" />
          </span>
          <nav className="flex items-center gap-2">
            <a
              href={BRAND.linkedin}
              target="_blank"
              rel="noreferrer"
              className="btn text-blue-100 hover:text-white"
            >
              <Linkedin size={16} /> {BRAND.author}
            </a>
            <Link to="/app/overview" className="btn bg-sun font-semibold text-navy hover:bg-sun-soft">
              Open Workspace <ArrowRight size={16} />
            </Link>
          </nav>
        </header>

        <section className="relative mx-auto grid max-w-6xl gap-12 px-6 pb-20 pt-14 lg:grid-cols-[1.15fr_0.85fr]">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs text-blue-100">
              <ShieldCheck size={14} className="text-emerald-400" /> 100% local · zero paid APIs · synthetic
              data
            </div>
            <h1 className="mt-6 text-5xl font-semibold leading-[1.05] tracking-tight md:text-6xl">
              ForecastLab
              <span className="mt-3 block bg-gradient-to-r from-sun via-sun-soft to-white bg-clip-text text-3xl text-transparent md:text-[40px]">
                AI Demand Planning &amp; S&amp;OP Decision Intelligence
              </span>
            </h1>
            <p className="mt-6 max-w-xl text-[17px] leading-relaxed text-blue-100">
              From raw sales history to an executive S&amp;OP decision: data quality, model competition,
              probabilistic forecasts, commercial scenarios, target feasibility, forecast value added —
              explained by a local AI analyst.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                to="/app/overview"
                className="btn bg-sun px-5 py-3 text-base font-semibold text-navy hover:bg-sun-soft"
              >
                Open Workspace <ArrowRight size={18} />
              </Link>
              <Link
                to="/app/data"
                className="btn border border-white/20 px-5 py-3 text-base text-white hover:bg-white/10"
              >
                <FileSpreadsheet size={18} /> Upload your data
              </Link>
            </div>
            <div className="mt-10 grid max-w-lg grid-cols-3 gap-6 border-t border-white/10 pt-6">
              <div>
                <div className="text-2xl font-semibold">{ov?.n_series ?? "—"}</div>
                <div className="text-xs text-blue-200/80">Customer × SKU series</div>
              </div>
              <div>
                <div className="text-2xl font-semibold">{meta?.models.length ?? 15}</div>
                <div className="text-xs text-blue-200/80">Competing models</div>
              </div>
              <div>
                <div className="text-2xl font-semibold">
                  {ov?.kpis?.accuracy != null ? pct(ov.kpis.accuracy) : "—"}
                </div>
                <div className="text-xs text-blue-200/80">Backtest accuracy</div>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-white/15 bg-white/[0.06] p-6 backdrop-blur">
            <div className="text-xs font-semibold uppercase tracking-[0.14em] text-blue-200/80">
              Demo workspace
            </div>
            <div className="mt-4 flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 p-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-sun text-sm font-semibold text-navy">
                DP
              </div>
              <div>
                <div className="text-sm font-semibold">Demand Planner (demo)</div>
                <div className="text-xs text-blue-200/80">
                  ForecastLab Demo Co. · 60 months of synthetic history
                </div>
              </div>
            </div>
            <ul className="mt-5 space-y-2.5 text-sm text-blue-100">
              {[
                "Rolling-origin backtest & champion/challenger",
                "P10 / P50 / P90 probabilistic forecast",
                "Commercial overrides → consensus",
                "Is the target realistic? Feasibility engine",
                "FVA: do planner overrides add value?",
              ].map((t) => (
                <li key={t} className="flex items-start gap-2">
                  <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-400" /> {t}
                </li>
              ))}
            </ul>
            <Link to="/app/overview" className="btn mt-6 w-full bg-white py-2.5 text-ink hover:bg-slate-100">
              Enter demo workspace <ArrowRight size={16} />
            </Link>
            <div className="mt-6 border-t border-white/10 pt-5 text-xs text-blue-200/80">
              <div className="text-blue-200/60">Developed by</div>
              <div className="mt-0.5 text-sm font-semibold text-white">{BRAND.author}</div>
              <div className="mt-0.5">{BRAND.titleEn}</div>
              <a
                href={BRAND.linkedin}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-flex items-center gap-1 text-sun hover:underline"
              >
                <Linkedin size={13} /> {BRAND.linkedinLabel}
              </a>
            </div>
          </div>
        </section>
      </div>

      <section className="mx-auto max-w-6xl px-6 py-14">
        <div className="grid gap-4 md:grid-cols-4">
          {PILLARS.map(({ icon: Icon, title, text }) => (
            <div key={title} className="rounded-xl border border-white/10 bg-white/[0.03] p-5">
              <Icon size={20} className="text-sun" />
              <div className="mt-3 font-semibold">{title}</div>
              <p className="mt-1.5 text-sm leading-relaxed text-blue-200/80">{text}</p>
            </div>
          ))}
        </div>

        <div className="mt-14">
          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-blue-200/80">
            The decision pipeline
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {STORY.map((s, i) => (
              <div key={s} className="flex items-center gap-2">
                <span className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white/90">
                  {s}
                </span>
                {i < STORY.length - 1 && <ArrowRight size={14} className="text-blue-200/50" />}
              </div>
            ))}
          </div>
        </div>

        <div className="mt-14 grid gap-4 md:grid-cols-3">
          {[
            {
              icon: Database,
              t: "React + TypeScript + FastAPI + DuckDB",
              d: "Decoupled full-stack architecture, Docker-ready.",
            },
            {
              icon: BrainCircuit,
              t: "Local AI (Ollama)",
              d: "Intent → semantic query → engines → grounded explanation.",
            },
            {
              icon: Gauge,
              t: "Model governance",
              d: "Model registry, run registry, dataset versioning, FVA.",
            },
          ].map(({ icon: Icon, t, d }) => (
            <div key={t} className="flex gap-3 rounded-xl border border-white/10 p-4">
              <Icon size={18} className="mt-0.5 shrink-0 text-sun" />
              <div>
                <div className="text-sm font-semibold">{t}</div>
                <div className="text-sm text-blue-200/80">{d}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-white/10 bg-navy-dark py-8 text-center text-xs text-blue-200/80">
        <div className="text-sm font-semibold text-white">ForecastLab</div>
        <div className="mt-1">
          {BRAND.signatureEn} · {BRAND.titleEn}
        </div>
        <div className="mt-0.5 text-blue-200/60">
          {BRAND.signaturePt} · {BRAND.titlePt}
        </div>
        <a
          href={BRAND.linkedin}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-flex items-center gap-1 text-sun hover:underline"
        >
          <Linkedin size={13} /> {BRAND.linkedinLabel}
        </a>
        <div className="mt-3 text-blue-200/50">
          All data is synthetic and fictitious. No real company, customer or product is represented.
        </div>
      </footer>
    </div>
  );
}
