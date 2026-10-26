/**
 * Global acceptance of the journey (spec §6.1.3–4, §5 F1 final step).
 *
 * Renders the whole App (sidebar + topbar included) at Entrada, every Relatório chapter and Desvios
 * (both lenses, drawer open) with the real-payload fixtures, then checks:
 * - visual budget: Entrada ≤ 5, each chapter exactly 1, Desvios exactly 5 `[data-visual]` blocks,
 *   each with a non-empty `data-question`;
 * - no grid row holds more than 4 KpiCards;
 * - no whole-word English UI term in the rendered text, aria-labels or titles;
 * - the journey sources contain no `truncate`, `line-clamp` or `border-l-` (nor emoji).
 */
import { configure, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Cmp } from "../lib/deviationsUrl";
import { LENS_OF } from "../lib/deviationsUrl";
import type { Story } from "../types/story";
import exceptionsForecastFx from "./fixtures/deviations-exceptions-forecast.json";
import exceptionsPlanFx from "./fixtures/deviations-exceptions.json";
import focusForecastFx from "./fixtures/deviations-focus-forecast.json";
import focusPlanFx from "./fixtures/deviations-focus-plan.json";
import seriesForecastFx from "./fixtures/deviations-series-forecast.json";
import seriesPlanFx from "./fixtures/deviations-series.json";
import summaryForecastFx from "./fixtures/deviations-summary-forecast.json";
import summaryPlanFx from "./fixtures/deviations-summary-plan.json";
import storyFixture from "./fixtures/story.json";
import trustFixtures from "./fixtures/trust.json";
import { journeyFixture, mockApi, shellRoutes, type MockRequest } from "./mockApi";
import { renderWithProviders } from "./render";

// Whole-App renders (shell + lazy page + 5 panels) are slow under a parallel suite run.
vi.setConfig({ testTimeout: 30_000 });
configure({ asyncUtilTimeout: 8_000 });

// jsdom has no canvas: ECharts-based charts render a labelled placeholder.
vi.mock("../charts/EChart", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../charts/EChart")>();
  const { createElement } = await import("react");
  return {
    ...actual,
    EChart: (props: { ariaLabel?: string }) =>
      createElement("div", { role: "img", "aria-label": props.ariaLabel, "data-testid": "echart" }),
  };
});

/* ------------------------------------------------------------------ fixtures */

const CHAPTERS = ["resumo", "realizado", "precisao", "projecao", "gap", "meta", "decisoes"] as const;

/** Rendered-text words that must never appear (spec §6.1.4); whole words, any case. */
const ENGLISH = ["Budget", "Target", "Forecast error", "Loading", "Error", "Next", "Previous", "Revenue"];

const clone = <T,>(v: unknown): T => structuredClone(v) as T;

const ACTIVE_DATASET = {
  dataset_version: "dataset_2026_10_v01",
  name: "Base sintética de demonstração (seed 42)",
  source: "synthetic_generator",
  file_name: null,
  created_at: "2026-10-26",
  n_rows: 12664,
  n_series: 220,
  n_skus: 24,
  n_customers: 14,
  start_date: "2021-10-01",
  end_date: "2026-09-01",
  quality_score: 100,
  quality_label: "Excelente",
  status: "valid",
  is_active: true,
  plan_source: "Orçamento anual e metas de vendas sintéticos",
  validation: {
    status: "valid",
    can_forecast: true,
    blocking_message: null,
    summary: {},
    quality: { completeness: 100, consistency: 100, historical_depth: 100, granularity: 100, overall: 100 },
    issues: [],
    column_mapping: {},
    missing_optional: [],
  },
};

const DIMENSIONS = {
  region: ["Centro-Oeste", "Nordeste", "Norte", "Sudeste", "Sul"],
  channel: ["Atacarejo", "E-commerce", "Farma", "Varejo Moderno"],
  customer: [],
  category: ["Bebidas", "Higiene", "Snacks"],
  brand: [],
  sku: [],
  customers: [],
  series: [],
  last_actual: "2026-09-01",
  horizon: [],
};

const isForecast = (req: MockRequest) => LENS_OF[(req.params.get("cmp") ?? "fc_pl") as Cmp] === "previsao";

/** Every request the shell and the three journey pages make. */
function journeyApi() {
  return mockApi({
    ...shellRoutes(journeyFixture("pronto"), { critical: 1, high: 2 }),
    "/api/data/active": ACTIVE_DATASET,
    "/api/models/trust": clone(trustFixtures.confiavel),
    "/api/story": clone<Story>(storyFixture),
    "/api/data/dimensions": DIMENSIONS,
    "/api/deviations/summary": (r: MockRequest) => clone(isForecast(r) ? summaryForecastFx : summaryPlanFx),
    "/api/deviations/focus": (r: MockRequest) => clone(isForecast(r) ? focusForecastFx : focusPlanFx),
    "/api/deviations/exceptions": (r: MockRequest) =>
      clone(isForecast(r) ? exceptionsForecastFx : exceptionsPlanFx),
    "/api/deviations/series": (r: MockRequest) => clone(isForecast(r) ? seriesForecastFx : seriesPlanFx),
  });
}

/* ------------------------------------------------------------------- checks */

/** `[data-visual]` blocks of the page (the drawer and modals are not counted). */
function visualBlocks(): HTMLElement[] {
  return [...document.querySelectorAll<HTMLElement>("[data-visual]")].filter(
    (el) => !el.closest('[role="dialog"]'),
  );
}

function expectQuestions(blocks: HTMLElement[]) {
  for (const b of blocks) {
    const q = b.getAttribute("data-question") ?? "";
    expect(q.trim(), `data-question de ${b.getAttribute("data-visual")}`).not.toBe("");
  }
}

/** Largest `grid-cols-N` (any breakpoint) of a container, or null when it sets none. */
function maxGridCols(el: Element): number | null {
  const ns = [...el.classList]
    .map((c) => /(?:^|:)grid-cols-(\d+)$/.exec(c)?.[1])
    .filter((n): n is string => !!n)
    .map(Number);
  return ns.length ? Math.max(...ns) : null;
}

/** No grid row holds more than 4 KpiCards: a grid declares ≤ 4 columns; any other row holds ≤ 4. */
function expectKpiRowsOfAtMost4() {
  const parents = new Set(
    [...document.querySelectorAll("[data-kpi]")].map((k) => k.parentElement as HTMLElement),
  );
  for (const p of parents) {
    const n = [...p.children].filter((c) => c.hasAttribute("data-kpi")).length;
    const cols = maxGridCols(p);
    if (p.classList.contains("grid") && cols !== null) expect(cols, p.className).toBeLessThanOrEqual(4);
    else expect(n, p.className).toBeLessThanOrEqual(4);
  }
}

/** No English UI term in the rendered text, nor in aria-labels, titles and placeholders. */
function expectNoEnglish() {
  const attrs = [...document.querySelectorAll("[aria-label],[title],[placeholder],[alt]")].flatMap((el) =>
    ["aria-label", "title", "placeholder", "alt"].map((a) => el.getAttribute(a) ?? ""),
  );
  const text = [document.body.textContent ?? "", ...attrs].join("\n");
  for (const w of ENGLISH) expect(text, w).not.toMatch(new RegExp(`\\b${w}\\b`, "i"));
  expect(text).not.toMatch(/\bundefined\b|\bNaN\b|\[object Object\]/);
}

/* -------------------------------------------------------------------- tests */

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

describe("journey · global visual budget and copy (spec §6.1.3–4)", () => {
  it("Entrada: ≤ 5 visual blocks with questions, KPI rows ≤ 4, pt-BR only", async () => {
    journeyApi();
    renderWithProviders(undefined, { route: "/app/entrada" });
    await screen.findByRole("heading", { level: 1, name: "Dados e modelos" });
    // the three steps, with the trust verdict loaded
    await screen.findByText(trustFixtures.confiavel.verdict.headline);
    const blocks = visualBlocks();
    expect(blocks.length).toBeGreaterThanOrEqual(1);
    expect(blocks.length).toBeLessThanOrEqual(5);
    expectQuestions(blocks);
    // the trust step: exactly 4 KPI cards (spec §2.1, F3)
    expect(document.querySelectorAll("[data-kpi]")).toHaveLength(4);
    expectKpiRowsOfAtMost4();
    expectNoEnglish();
  });

  it.each(CHAPTERS)("Relatório · %s: exactly 1 visual block with a question, pt-BR only", async (id) => {
    const story = storyFixture as unknown as Story;
    const chapter = story.chapters.find((c) => c.id === id)!;
    journeyApi();
    renderWithProviders(undefined, { route: `/app/relatorio/${id}` });
    const h1 = await screen.findByRole("heading", { level: 1 });
    expect(h1).toHaveTextContent(id === "resumo" ? story.governing_thought : chapter.headline);
    const blocks = visualBlocks();
    expect(blocks).toHaveLength(1);
    expectQuestions(blocks);
    expect(document.querySelectorAll("[data-kpi]")).toHaveLength(id === "resumo" ? 4 : 0);
    expectKpiRowsOfAtMost4();
    expectNoEnglish();
  });

  it.each([
    ["Plano", "/app/desvios?serie=Litoral%20Market%7CSKU-30102"],
    ["Previsão", "/app/desvios?lente=previsao&cmp=ac_fc&serie=Litoral%20Market%7CSKU-30102"],
  ])(
    "Desvios · lente %s: exactly 5 visual blocks, ≤ 4 KPI cards, pt-BR only (drawer open)",
    async (_, route) => {
      journeyApi();
      renderWithProviders(undefined, { route });
      const drawer = await screen.findByRole("dialog", { name: /Litoral Market · SKU-30102/ });
      await within(drawer).findByText("Evidências");
      // all five panels loaded (the exceptions table has its rows)
      await screen.findAllByRole("button", { name: /^Ações/ });
      const blocks = visualBlocks();
      expect(blocks.map((b) => b.getAttribute("data-visual"))).toEqual([
        "kpis",
        "onde",
        "porque",
        "quando",
        "excecoes",
      ]);
      expectQuestions(blocks);
      expect(blocks[0].querySelectorAll("[data-kpi]")).toHaveLength(4);
      expectKpiRowsOfAtMost4();
      expectNoEnglish();
    },
  );
});

describe("journey · sources (spec §6.1.4)", () => {
  it("no truncate, line-clamp, side stripe or emoji in the journey files", () => {
    const sources = import.meta.glob(
      [
        "../pages/{Entrada,Relatorio,Desvios}.tsx",
        "../components/{entrada,story,desvios,journey}/**/*.{ts,tsx}",
        "../charts/{BridgeChart,VarianceColumns,VarianceBars,CauseBars,BacktestLine,FeasibilityRange}.tsx",
      ],
      { query: "?raw", import: "default", eager: true },
    ) as Record<string, string>;
    // 3 pages + the 4 component folders + 6 charts
    expect(Object.keys(sources).length).toBeGreaterThanOrEqual(30);
    for (const [file, src] of Object.entries(sources)) {
      expect(src, file).not.toMatch(/\btruncate\b|line-clamp|border-l-/);
      expect(src, file).not.toMatch(/\p{Extended_Pictographic}/u);
    }
  });

  it("KpiCard (ui.tsx) neither truncates nor clamps its label", () => {
    const ui = import.meta.glob("../components/ui.tsx", {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>;
    const src = Object.values(ui)[0];
    const start = src.indexOf("export function KpiCard");
    const end = src.indexOf("\nexport function", start + 1);
    expect(start).toBeGreaterThan(-1);
    const kpi = src.slice(start, end === -1 ? undefined : end);
    expect(kpi).not.toMatch(/\btruncate\b|line-clamp|border-l-/);
  });
});
