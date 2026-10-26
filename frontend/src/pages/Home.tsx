import {
  ArrowRight,
  Bot,
  BrainCircuit,
  ChartLine,
  CircleCheckBig,
  Crosshair,
  Database,
  FileSpreadsheet,
  Gauge,
  Goal,
  Layers,
  Linkedin,
  ShieldCheck,
  Sparkles,
  SquareSplitHorizontal,
  Target,
  Trophy,
} from "lucide-react";
import { Link } from "react-router-dom";

import { ClientLogo, Logo } from "../components/Layout";
import { ClassBadge, IconTile } from "../components/ui";
import { useGet } from "../hooks/useApi";
import { BRAND } from "../lib/branding";
import type { Tone } from "../lib/colors";
import { full, pct } from "../lib/format";
import { t } from "../lib/labels";
import { ROUTES } from "../lib/routes";

const PILLARS: { icon: typeof Bot; tone: Tone; title: string; text: string }[] = [
  {
    icon: ChartLine,
    tone: "blue",
    title: "Acurácia do forecast",
    text: "15 modelos estatísticos e de machine learning competem em cada série em um backtest com origem móvel.",
  },
  {
    icon: SquareSplitHorizontal,
    tone: "green",
    title: "Planejamento de cenários",
    text: "Simulações what-if com elasticidades estimadas de preço, distribuição e promoção.",
  },
  {
    icon: Target,
    tone: "yellow",
    title: "S&OP",
    text: "Consenso vs orçamento vs meta, riscos e oportunidades e viabilidade das metas.",
  },
  {
    icon: Bot,
    tone: "navy",
    title: "Analista de IA",
    text: "Pergunte em linguagem natural: a IA local explica os resultados e todo número vem dos motores de cálculo.",
  },
];

const PIPELINE = [
  "Dados históricos",
  "Qualidade dos dados",
  "Modelagem estatística",
  "Competição de modelos",
  "Forecast",
  "Ajustes comerciais",
  "Cenários",
  "S&OP",
  "Inteligência de decisão",
  "Explicação por IA",
];

const DEMO_FEATURES = [
  "Backtest com origem móvel, Campeão e Desafiante",
  "Forecast probabilístico P10 / P50 / P90",
  "Ajustes comerciais → forecast de consenso",
  "A meta é realista? Motor de viabilidade",
  "FVA: os ajustes dos planejadores agregam valor?",
];

const TECH: { icon: typeof Bot; tone: Tone; title: string; text: string }[] = [
  {
    icon: Database,
    tone: "teal",
    title: "React + TypeScript + FastAPI + DuckDB",
    text: "Arquitetura full-stack desacoplada, pronta para Docker.",
  },
  {
    icon: BrainCircuit,
    tone: "purple",
    title: "IA local (Ollama)",
    text: "Intenção → consulta semântica → motores de cálculo → explicação fundamentada nos dados.",
  },
  {
    icon: Gauge,
    tone: "orange",
    title: "Governança de modelos",
    text: "Registro de modelos, registro de execuções, versionamento de dados e FVA.",
  },
];

interface OverviewSummary {
  has_run: boolean;
  n_series: number;
  kpis?: { accuracy: number | null };
  champions?: { model: string; count: number }[];
  feasibility?: { available: boolean; probability?: number; classification?: string };
}

const GLASS =
  "rounded-3xl border border-white/80 bg-white/70 shadow-[0_18px_40px_-20px_rgba(45,50,119,0.28),0_2px_6px_-2px_rgba(45,50,119,0.06)] backdrop-blur-xl";

export default function Home() {
  const { data: ov } = useGet<OverviewSummary>("/api/overview", undefined, { retry: false });
  const { data: meta } = useGet<{ models: unknown[] }>("/api/meta", undefined, { retry: false });
  const champion = ov?.champions?.[0];
  const feas = ov?.feasibility?.available ? ov.feasibility : undefined;

  const stats = [
    {
      icon: <Layers />,
      tone: "blue" as Tone,
      value: ov?.n_series != null ? full(ov.n_series) : "—",
      label: "Séries Cliente × SKU",
    },
    {
      icon: <Trophy />,
      tone: "yellow" as Tone,
      value: full(meta?.models.length ?? 15),
      label: "Modelos competindo",
    },
    {
      icon: <Crosshair />,
      tone: "green" as Tone,
      value: ov?.kpis?.accuracy != null ? pct(ov.kpis.accuracy) : "—",
      label: "Acurácia de backtest",
    },
  ];

  return (
    <div className="relative min-h-screen overflow-hidden text-ink">
      {/* Pastel light blobs */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="absolute -left-48 -top-48 h-[560px] w-[560px] rounded-full bg-[#bcd5ff] opacity-70 blur-3xl" />
        <div className="absolute -right-32 -top-24 h-[480px] w-[480px] rounded-full bg-[#fff1a1] opacity-80 blur-3xl" />
        <div className="absolute left-[38%] top-[380px] h-[520px] w-[520px] rounded-full bg-[#e2dbff] opacity-70 blur-3xl" />
        <div className="absolute -left-24 top-[1100px] h-[420px] w-[420px] rounded-full bg-[#d7f3ff] opacity-70 blur-3xl" />
        <div className="absolute -right-24 top-[1500px] h-[420px] w-[420px] rounded-full bg-[#fff6c4] opacity-70 blur-3xl" />
      </div>

      <div className="relative">
        {/* ------------------------------------------------------------ header */}
        <header className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-6">
          <span className="flex items-center gap-3">
            <Logo size={36} />
            {/* ClientLogo is styled for dark backgrounds: darken its divider, lift its white plate. */}
            <span className="contents [&_.bg-white]:shadow-[0_6px_16px_-10px_rgba(45,50,119,0.5)] [&_[aria-hidden]]:bg-line">
              <ClientLogo variant="inline" />
            </span>
          </span>
          <nav className="flex items-center gap-2">
            <a
              href={BRAND.linkedin}
              target="_blank"
              rel="noreferrer"
              className="btn-ghost hidden sm:inline-flex"
              title={BRAND.titlePt}
            >
              <Linkedin size={16} className="text-[#0a66c2]" /> {BRAND.author}
            </a>
            <Link to={ROUTES.entrada()} className="btn-primary">
              Começar <ArrowRight size={16} />
            </Link>
          </nav>
        </header>

        {/* -------------------------------------------------------------- hero */}
        <section className="mx-auto grid max-w-6xl items-center gap-12 px-6 pb-16 pt-10 lg:grid-cols-[1.12fr_0.88fr] lg:pt-14">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/80 bg-white/75 px-3.5 py-1.5 text-xs font-semibold text-ink-2 shadow-[0_6px_16px_-10px_rgba(45,50,119,0.45)] backdrop-blur">
              <ShieldCheck size={14} className="text-emerald-600" />
              100% local · sem APIs pagas · dados sintéticos
            </div>
            <h1 className="mt-6 text-5xl font-extrabold leading-[1.04] tracking-tight text-navy md:text-6xl">
              ForecastLab
              <span className="mt-3 block bg-gradient-to-r from-[#3483fa] via-[#6a5cff] to-[#2d3277] bg-clip-text pb-1 text-[28px] font-bold leading-tight text-transparent md:text-[38px]">
                Planejamento de Demanda &amp; S&amp;OP com Inteligência de Decisão
              </span>
            </h1>
            <div className="mt-5 h-1.5 w-24 rounded-full bg-gradient-to-r from-[#ffe600] to-[#ffc400] shadow-[0_6px_14px_-6px_rgba(240,190,0,0.9)]" />
            <p className="mt-6 max-w-xl text-[17px] leading-relaxed text-ink-2">
              Do histórico de vendas à decisão executiva de S&amp;OP: qualidade dos dados, competição de
              modelos, forecast probabilístico, cenários comerciais, viabilidade de metas e valor agregado dos
              ajustes (FVA) — tudo explicado por um analista de IA local.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to={ROUTES.entrada()} className="btn-primary px-6 py-3 text-base">
                Começar <ArrowRight size={18} />
              </Link>
              <Link to={ROUTES.entrada({ acao: "carregar" })} className="btn-secondary px-6 py-3 text-base">
                <FileSpreadsheet size={18} className="text-emerald-600" /> Carregar meus dados
              </Link>
            </div>
            <div className="mt-10 grid max-w-xl gap-3 sm:grid-cols-3">
              {stats.map((s) => (
                <div key={s.label} className={`${GLASS} flex items-center gap-3 px-4 py-3.5`}>
                  <IconTile icon={s.icon} tone={s.tone} size="sm" />
                  <div className="min-w-0">
                    <div className="whitespace-nowrap text-xl font-bold leading-tight text-ink">
                      {s.value}
                    </div>
                    <div className="text-[11.5px] font-medium leading-snug text-muted">{s.label}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Demo workspace card */}
          <div className="relative">
            {champion && (
              <div
                className={`${GLASS} absolute -left-10 -top-6 z-10 hidden items-center gap-3 bg-white/90 px-4 py-3 xl:flex`}
              >
                <IconTile icon={<Trophy />} tone="yellow" size="sm" />
                <div>
                  <div className="text-[11px] font-medium text-muted">Modelo campeão mais frequente</div>
                  <div className="text-sm font-bold text-ink">{t.model(champion.model)}</div>
                </div>
              </div>
            )}
            {feas?.probability != null && (
              <div
                className={`${GLASS} absolute -bottom-7 -right-8 z-10 hidden items-center gap-3 bg-white/90 px-4 py-3 xl:flex`}
              >
                <IconTile icon={<Goal />} tone="green" size="sm" />
                <div>
                  <div className="text-[11px] font-medium text-muted">Chance de bater a meta 12M</div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-ink">{pct(feas.probability, 0)}</span>
                    <ClassBadge value={feas.classification} />
                  </div>
                </div>
              </div>
            )}

            <div className={`${GLASS} relative overflow-hidden p-7`}>
              <div className="pointer-events-none absolute -right-16 -top-16 h-44 w-44 rounded-full bg-gradient-to-br from-[#dbe8ff] to-transparent" />
              <div className="relative">
                <div className="label-xs">Workspace de demonstração</div>
                <div className="mt-4 flex items-center gap-3 rounded-2xl border border-white/80 bg-white/80 p-4 shadow-[0_8px_20px_-14px_rgba(45,50,119,0.4)]">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-[#3483fa] to-[#2d3277] text-sm font-bold text-white shadow-[0_10px_20px_-8px_rgba(45,50,119,0.7)]">
                    PD
                  </div>
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-ink">Planejador de Demanda (demo)</div>
                    <div className="text-xs text-muted">
                      ForecastLab Demo Ltda. · 60 meses de histórico sintético
                    </div>
                  </div>
                </div>
                <ul className="mt-5 space-y-3 text-sm text-ink-2">
                  {DEMO_FEATURES.map((item) => (
                    <li key={item} className="flex items-start gap-3">
                      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#e3f7ec] text-[#0d7a47]">
                        <CircleCheckBig size={13} strokeWidth={2.5} />
                      </span>
                      {item}
                    </li>
                  ))}
                </ul>
                <Link to={ROUTES.entrada()} className="btn-primary mt-6 w-full py-3">
                  Começar <ArrowRight size={16} />
                </Link>
                <div className="mt-6 flex items-center gap-3 border-t border-line pt-5">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-sun text-xs font-bold text-navy shadow-[0_8px_16px_-8px_rgba(240,190,0,0.9)]">
                    WS
                  </div>
                  <div className="min-w-0 text-xs">
                    <div className="text-muted">Desenvolvido por</div>
                    <div className="text-sm font-semibold text-ink">{BRAND.author}</div>
                    <div className="mt-0.5 leading-snug text-muted">{BRAND.titlePt}</div>
                    <a
                      href={BRAND.linkedin}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1.5 inline-flex items-center gap-1 font-semibold text-brand hover:underline"
                    >
                      <Linkedin size={13} /> {BRAND.linkedinLabel}
                    </a>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ----------------------------------------------------------- pillars */}
        <section className="mx-auto max-w-6xl px-6 py-12">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-1.5 rounded-full bg-white/80 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.12em] text-brand shadow-[0_4px_12px_-6px_rgba(52,131,250,0.5)]">
              <Sparkles size={13} /> O que o ForecastLab faz
            </div>
            <h2 className="mt-3 text-3xl font-bold tracking-tight text-ink">
              Do dado à decisão, em um só lugar
            </h2>
            <p className="mt-2 text-[15px] leading-relaxed text-muted">
              Quatro pilares que levam o planejamento de demanda do histórico bruto à reunião executiva de
              S&amp;OP.
            </p>
          </div>
          <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {PILLARS.map(({ icon: Icon, tone, title, text }) => (
              <div
                key={title}
                className={`${GLASS} p-6 transition duration-200 hover:-translate-y-1 hover:shadow-[0_24px_44px_-20px_rgba(45,50,119,0.35)]`}
              >
                <IconTile icon={<Icon />} tone={tone} size="lg" />
                <div className="mt-5 text-base font-bold text-ink">{title}</div>
                <p className="mt-2 text-sm leading-relaxed text-muted">{text}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ---------------------------------------------------------- pipeline */}
        <section className="mx-auto max-w-6xl px-6 py-6">
          <div className={`${GLASS} p-7`}>
            <div className="flex flex-wrap items-center gap-3">
              <IconTile icon={<Sparkles />} tone="purple" size="sm" />
              <div>
                <div className="text-base font-bold text-ink">O pipeline de decisão</div>
                <div className="text-xs text-muted">
                  Cada etapa alimenta a próxima — do dado bruto à explicação por IA.
                </div>
              </div>
            </div>
            <ol className="mt-6 flex flex-wrap items-center gap-2">
              {PIPELINE.map((step, i) => (
                <li key={step} className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-2 rounded-full border border-white/90 bg-white/90 py-1.5 pl-1.5 pr-3.5 text-sm font-medium text-ink shadow-[0_6px_14px_-10px_rgba(45,50,119,0.45)]">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-[#7db4ff] to-[#3483fa] text-[11px] font-bold text-white">
                      {i + 1}
                    </span>
                    {step}
                  </span>
                  {i < PIPELINE.length - 1 && <ArrowRight size={14} className="text-muted" aria-hidden />}
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* -------------------------------------------------------------- tech */}
        <section className="mx-auto max-w-6xl px-6 py-6">
          <div className="grid gap-5 md:grid-cols-3">
            {TECH.map(({ icon: Icon, tone, title, text }) => (
              <div key={title} className={`${GLASS} flex gap-4 p-5`}>
                <IconTile icon={<Icon />} tone={tone} size="md" />
                <div className="min-w-0">
                  <div className="text-sm font-bold text-ink">{title}</div>
                  <div className="mt-1 text-sm leading-relaxed text-muted">{text}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* --------------------------------------------------------------- CTA */}
        <section className="mx-auto max-w-6xl px-6 pb-14 pt-8">
          <div className="relative overflow-hidden rounded-[32px] bg-gradient-to-br from-[#2d3277] via-[#3a4bb5] to-[#3483fa] px-8 py-10 text-white shadow-[0_28px_60px_-28px_rgba(45,50,119,0.85)] md:px-12">
            <div className="pointer-events-none absolute -right-10 -top-14 h-56 w-56 rounded-full bg-white/10" />
            <div className="pointer-events-none absolute -bottom-20 right-40 h-44 w-44 rounded-full bg-[#ffe600]/20 blur-2xl" />
            <div className="relative flex flex-wrap items-center justify-between gap-6">
              <div className="max-w-xl">
                <div className="text-2xl font-bold tracking-tight md:text-3xl">Pronto para ver o plano?</div>
                <p className="mt-2 text-sm leading-relaxed text-blue-100">
                  Comece pela entrada: valide a base, veja os modelos competirem e abra o relatório executivo
                  — com a base de demonstração ou com a sua própria planilha de vendas.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <Link
                  to={ROUTES.entrada()}
                  className="btn bg-sun px-6 py-3 text-base font-bold text-navy shadow-[0_10px_22px_-10px_rgba(255,214,0,0.9)] hover:brightness-105"
                >
                  Começar <ArrowRight size={18} />
                </Link>
                <Link
                  to={ROUTES.entrada({ acao: "carregar" })}
                  className="btn border border-white/30 px-6 py-3 text-base text-white hover:bg-white/10"
                >
                  <FileSpreadsheet size={18} /> Carregar meus dados
                </Link>
              </div>
            </div>
          </div>
        </section>

        {/* ------------------------------------------------------------ footer */}
        <footer className="border-t border-white/80 bg-white/60 py-8 text-center text-xs text-muted backdrop-blur">
          <div className="flex justify-center">
            <Logo size={28} />
          </div>
          <div className="mt-3 text-ink-2">
            <span className="font-semibold text-ink">{BRAND.signaturePt}</span> · {BRAND.titlePt}
          </div>
          <div className="mt-0.5" lang="en">
            {BRAND.signatureEn} · {BRAND.titleEn}
          </div>
          <a
            href={BRAND.linkedin}
            target="_blank"
            rel="noreferrer"
            className="mt-2 inline-flex items-center gap-1 font-semibold text-brand hover:underline"
          >
            <Linkedin size={13} /> {BRAND.linkedinLabel}
          </a>
          <div className="mt-3 text-muted/80">
            Todos os dados são sintéticos e fictícios. Nenhuma empresa, cliente ou produto real é
            representado.
          </div>
        </footer>
      </div>
    </div>
  );
}
