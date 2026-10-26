/**
 * Secondary pages (spec §3 / §5 F6): Bases de dados, Workspace de forecast, Modelos e FVA,
 * Cenários e metas and Alertas. Network is stubbed by pathname with `mockApi`; the ECharts canvas
 * is replaced by a plain element (jsdom has no canvas).
 */
import { configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import Alerts from "../pages/Alerts";
import Data from "../pages/Data";
import Forecasting from "../pages/Forecasting";
import ModelPerformance from "../pages/ModelPerformance";
import Scenarios from "../pages/Scenarios";
import { mockApi, type MockHandler } from "./mockApi";
import { renderWithProviders } from "./render";

vi.mock("../charts/EChart", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../charts/EChart")>();
  return {
    ...mod,
    EChart: ({ ariaLabel }: { ariaLabel?: string }) => <div role="img" aria-label={ariaLabel} />,
  };
});

// Whole-page renders (first render of each page module) are slow under a parallel suite run: the
// default 5 s per test timed out the Workspace and Cenários tests on a loaded machine.
configure({ asyncUtilTimeout: 5000 });
vi.setConfig({ testTimeout: 20_000 });

/* ----------------------------------------------------------------- fixtures */

const HORIZON = [
  "2026-10-01",
  "2026-11-01",
  "2026-12-01",
  "2027-01-01",
  "2027-02-01",
  "2027-03-01",
  "2027-04-01",
  "2027-05-01",
  "2027-06-01",
  "2027-07-01",
  "2027-08-01",
  "2027-09-01",
];

const DIMENSIONS = {
  region: ["Nordeste", "Sudeste", "Sul"],
  channel: ["Varejo Moderno"],
  customer: ["Atlas Hipermercados", "Litoral Market", "Rede Horizonte Supermercados"],
  category: ["Bebidas"],
  brand: ["AquaViva"],
  sku: [{ sku: "SKU-10101", product: "AquaViva Água Mineral 500ml", category: "Bebidas", brand: "AquaViva" }],
  customers: [
    {
      customer: "Litoral Market",
      region: "Nordeste",
      channel: "Varejo Moderno",
      customer_location: "Recife/PE",
    },
  ],
  series: [],
  last_actual: "2026-09-01",
  horizon: HORIZON,
};

const SERIES_ID = "Litoral Market|SKU-10101";

const SERIES_LIST = [
  {
    series_id: SERIES_ID,
    customer: "Litoral Market",
    sku: "SKU-10101",
    product: "AquaViva Água Mineral 500ml",
    region: "Nordeste",
    channel: "Varejo Moderno",
    category: "Bebidas",
    brand: "AquaViva",
    series_type: "Seasonal",
    wmape: 0.142,
  },
];

const SERIES_DETAIL = {
  series_id: SERIES_ID,
  has_run: true,
  header: {
    sku: "SKU-10101",
    product: "AquaViva Água Mineral 500ml",
    customer: "Litoral Market",
    region: "Nordeste",
    channel: "Varejo Moderno",
    category: "Bebidas",
    brand: "AquaViva",
  },
  timeline: HORIZON.map((date) => ({ date, base: 100, consensus: 110, p10: 80, p90: 130 })),
  selection: {
    series_type: "Seasonal",
    classification_reason: "Força sazonal 0,72 ≥ 0,64",
    champion: "Regression",
    challenger: "ETS",
    wmape: 0.142,
    accuracy: 0.858,
    bias: -0.021,
    bias_class: "Balanced",
    challenger_wmape: 0.161,
    confidence: "High",
    confidence_score: 82,
    stability: 0.03,
    history_months: 60,
    candidates: ["Regression", "ETS", "Naive"],
  },
  next_month: { date: "2026-10-01", base: 100, consensus: 110, p10: 80, p90: 130 },
  leaderboard: [],
  backtest: [],
  overrides: [],
  baseline_vs_incremental: HORIZON.map((date) => ({ date, p50: 100, incremental: 10, consensus: 110 })),
};

const EVENT_LIBRARY = [
  { type: "Promoção", direction: "up", typical_uplift: 0.25, description: "Promoção de preço / encarte" },
  { type: "Merchandising", direction: "up", typical_uplift: 0.12, description: "Displays e pontas" },
];

const group = (key: string, value: string, fva_pp: number) => ({
  [key]: value,
  overrides: 10,
  improved_pct: 0.6,
  wmape_statistical: 0.2,
  wmape_consensus: 0.2 - fva_pp,
  fva_pp,
  fva_units: 100,
  avg_adjustment: 0.2,
});

const FVA = {
  available: true,
  stairstep: {
    naive: 0.273,
    statistical: 0.148,
    consensus: 0.137,
    fva_statistical_vs_naive: 0.125,
    fva_consensus_vs_statistical: 0.011,
  },
  monthly: [{ date: "2026-01-01", naive: 0.3, statistical: 0.15, consensus: 0.14 }],
  cells_evaluated: 2621,
  pending_overrides: 12,
  summary: {
    overrides: 368,
    improved: 205,
    worsened: 152,
    neutral: 11,
    value_added_pct: 0.557,
    wmape_statistical_overridden: 0.218,
    wmape_consensus_overridden: 0.154,
    fva_pp_overridden: 0.064,
    fva_units: 93856,
  },
  by_planner: [group("planner", "Trade Marketing", 0.075)],
  by_event_type: [group("event_type", "Promoção", 0.143), group("event_type", "Campanha", -0.126)],
  by_direction: [group("direction", "Upward", 0.072)],
  by_magnitude: [group("magnitude", "> 20%", 0.121)],
  overrides: [],
  examples: [
    {
      kind: "worst",
      customer: "Atlas Hipermercados",
      sku: "SKU-10101",
      date: "2026-03-01",
      planner: "Trade Marketing",
      event_type: "Promoção",
      statistical: 100,
      consensus: 130,
      actual: 90,
    },
  ],
};

const SCENARIO_PARAMS = {
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

const SCENARIOS = [
  {
    scenario_id: "SCN-BASE",
    name: "Base",
    kind: "base",
    description: "Consenso.",
    is_system: true,
    created_at: "2026-10-26",
    updated_at: "2026-10-26",
    params: SCENARIO_PARAMS,
  },
  {
    scenario_id: "SCN-AGGRESSIVE",
    name: "Agressivo",
    kind: "aggressive",
    description: "Mais distribuição.",
    is_system: false,
    created_at: "2026-10-26",
    updated_at: "2026-10-26",
    params: { ...SCENARIO_PARAMS, distribution_change_pct: 0.05 },
  },
];

const SIMULATION = {
  totals: {
    units: 8_900_000,
    revenue: 95_000_000,
    base_units: 8_840_000,
    base_revenue: 94_300_000,
    budget_revenue: 98_390_000,
    target_revenue: 106_000_000,
    vs_base_units: 0.007,
    vs_base_revenue: 0.0074,
    vs_budget_revenue: -0.034,
    vs_target_revenue: -0.104,
  },
  monthly: HORIZON.map((date) => ({ date, base_revenue: 7.8e6, scenario_revenue: 7.9e6 })),
  drivers: [{ lever: "distribution", units: 60_000 }],
};

const COMPARE = {
  rows: [{ scenario_id: "SCN-BASE", name: "Base", kind: "base", units: 8.84e6, revenue: 94.3e6 }],
  series: [{ scenario_id: "SCN-BASE", name: "Base", monthly: [] }],
};

const ELASTICITIES = {
  estimated: { Bebidas: { price_elasticity: -2.1, distribution_elasticity: 0.9, source: "estimated" } },
  synthetic_truth: { price_elasticity: { Bebidas: -2.0 } },
};

const VALIDATION = {
  status: "warnings",
  can_forecast: true,
  blocking_message: null,
  summary: {
    rows: 12664,
    n_skus: 24,
    n_customers: 14,
    n_series: 220,
    start_date: "2021-10-01",
    end_date: "2026-09-01",
    missing_values: {},
    duplicated_rows: 0,
    invalid_dates: 0,
    negative_values: 0,
    zero_demand_periods: 12,
    outliers: 3,
    history: { min_months: 18, median_months: 60, max_months: 60, short_series: 0 },
  },
  quality: { completeness: 100, consistency: 98, historical_depth: 100, granularity: 100, overall: 99 },
  issues: [{ severity: "warning", code: "outliers", message: "3 outliers", count: 3, examples: [] }],
  column_mapping: {},
  missing_optional: [],
};

const DATASET = {
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
  quality_score: 99,
  status: "warnings",
  is_active: true,
  plan_source: "Orçamento anual e metas de vendas sintéticos",
  validation: VALIDATION,
  active_run: "RUN-20261026-053746",
};

const alert = (type: string, entity: Record<string, string>, severity = "high") => ({
  id: `${type}-${Object.values(entity).join("-")}`,
  type,
  title: "",
  color: "red",
  icon: "",
  severity,
  entity,
  issue: "Problema de teste",
  magnitude: "WMAPE 41%",
  value: 0.41,
  potential_impact: 120_000,
  explanation: "Explicação de teste",
  recommendation: "Recomendação de teste",
});

const ALERTS = {
  summary: {
    total: 4,
    by_severity: { high: 2, medium: 1, low: 1 },
    by_type: { high_error: 1, target_above_p90: 1, challenger_improving: 1, opportunity: 1 },
  },
  alerts: [
    alert("high_error", {
      series_id: "Atlas Hipermercados|SKU-30103",
      customer: "Atlas Hipermercados",
      sku: "SKU-30103",
      product: "PuraPele Kit Presente",
      region: "Sudeste",
    }),
    alert("target_above_p90", { customer: "Litoral Market", region: "Nordeste" }),
    alert(
      "challenger_improving",
      {
        series_id: "Rede Horizonte Supermercados|SKU-10201",
        customer: "Rede Horizonte Supermercados",
        sku: "SKU-10201",
        product: "Frutalle Suco de Laranja 1L",
        region: "Sul",
      },
      "medium",
    ),
    alert("opportunity", { customer: "ClickCesta", region: "Sudeste" }, "low"),
  ],
};

/* ------------------------------------------------------------------ helpers */

const COMMON: Record<string, MockHandler> = {
  "/api/data/dimensions": DIMENSIONS,
  "/api/forecast/job": null,
};

/** Renders `page` mounted at `path`, plus a stub deep-dive route to land on. */
function renderPage(page: ReactElement, path: string, route: string) {
  return renderWithProviders(
    <Routes>
      <Route path={path} element={page} />
      <Route path="/app/desvios" element={<div>Deep dive dos desvios</div>} />
    </Routes>,
    { route },
  );
}

/**
 * KpiCards are the `card … px-5 py-5` tiles of `components/ui.tsx`. Every grid that holds them must
 * stay at ≤ 4 columns (brand rule); returns how many KpiCards were found.
 */
function expectKpiRowsAtMostFour(container: HTMLElement): number {
  const kpis = Array.from(container.querySelectorAll<HTMLElement>("div.card.px-5.py-5"));
  for (const grid of new Set(kpis.map((k) => k.parentElement as HTMLElement))) {
    const cols = [...grid.className.matchAll(/grid-cols-(\d+)/g)].map((m) => Number(m[1]));
    expect(Math.max(1, ...cols)).toBeLessThanOrEqual(4);
    expect(grid.children.length).toBeLessThanOrEqual(4);
  }
  return kpis.length;
}

/* -------------------------------------------------------------------- tests */

describe("Workspace de forecast", () => {
  it("?mode=hierarchy lands on the deviation deep dive", async () => {
    const api = mockApi({});
    const { location } = renderPage(<Forecasting />, "/app/forecasting", "/app/forecasting?mode=hierarchy");
    expect(await screen.findByText("Deep dive dos desvios")).toBeInTheDocument();
    expect(location().pathname).toBe("/app/desvios");
    expect(api.calls).toHaveLength(0);
  });

  it("prefills the adjustment form from the URL", async () => {
    mockApi({
      ...COMMON,
      "/api/forecast/series": SERIES_LIST,
      "/api/forecast/series-detail": SERIES_DETAIL,
      "/api/overrides/event-library": EVENT_LIBRARY,
    });
    const route =
      "/app/forecasting?series=Litoral%20Market%7CSKU-10101&ajuste=1&mes=2026-12-01&evento=Promo%C3%A7%C3%A3o&uplift=0.2&comentario=Sugerido%20pelo%20deep%20dive";
    const { container } = renderPage(<Forecasting />, "/app/forecasting", route);

    expect(await screen.findByRole("heading", { name: "Workspace de forecast" })).toBeInTheDocument();
    const month = (await screen.findByLabelText("Mês")) as HTMLSelectElement;
    expect(month.value).toBe("2026-12-01");
    const event = screen.getByLabelText("Evento") as HTMLSelectElement;
    await waitFor(() => expect(event.value).toBe("Promoção"));
    expect((screen.getByLabelText("Uplift esperado (%)") as HTMLInputElement).value).toBe("20");
    expect((screen.getByLabelText("Comentário") as HTMLInputElement).value).toBe("Sugerido pelo deep dive");
    expect(screen.getByText(/Ajuste sugerido pelo deep dive/)).toBeInTheDocument();

    // Header stats: Campeão · Acurácia · Viés · Faixa P10–P90 (the 5th/6th stats are gone).
    const header = within(screen.getByText("Modelo campeão").closest("section")!);
    expect(header.getByText("Acurácia do forecast")).toBeInTheDocument();
    expect(header.getByText("Viés")).toBeInTheDocument();
    expect(header.getByText(/^Faixa P10–P90/)).toBeInTheDocument();
    expect(header.queryByText(/^Próximo mês/)).not.toBeInTheDocument();
    expect(header.queryByText("WMAPE")).not.toBeInTheDocument();
    // No hierarchy tab and no "Base vs incremental" chart.
    expect(screen.queryByText("Explorador da hierarquia")).not.toBeInTheDocument();
    expect(screen.queryByText("Base vs incremental")).not.toBeInTheDocument();
    expectKpiRowsAtMostFour(container);
  });
});

describe("Cenários e metas", () => {
  const routes = (): Record<string, MockHandler> => ({
    ...COMMON,
    "/api/scenarios": SCENARIOS,
    "POST /api/scenarios/simulate": SIMULATION,
    "/api/scenarios/compare": COMPARE,
    "/api/scenarios/elasticities": ELASTICITIES,
    "POST /api/sop/allocation": { dimension: "region", method: "historical", total_target: 1, rows: [] },
  });

  it("opens a prefilled draft with the banner from the deep dive", async () => {
    const api = mockApi(routes());
    const { container } = renderPage(
      <Scenarios />,
      "/app/scenarios",
      "/app/scenarios?customer=Litoral%20Market&distribution_change_pct=0.1",
    );
    expect(
      await screen.findByText("Cenário pré-preenchido. Ajuste e salve se quiser mantê-lo."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Nome")).toHaveValue("Simulação a partir do deep dive");
    expect(screen.getByLabelText("Distribuição")).toHaveValue("0.1");
    expect(screen.getByLabelText("Escopo: cliente")).toHaveValue("Litoral Market");
    // The draft stays a new scenario: no saved scenario got selected over it.
    expect(screen.getByRole("button", { name: /Novo cenário/ })).toHaveAttribute("aria-pressed", "true");

    await waitFor(() => expect(api.count("POST /api/scenarios/simulate")).toBeGreaterThan(0));
    const body = api.requests("/api/scenarios/simulate")[0].body as {
      params: { scope: Record<string, string>; distribution_change_pct: number };
    };
    expect(body.params.scope).toEqual({ customer: "Litoral Market" });
    expect(body.params.distribution_change_pct).toBe(0.1);

    // 4 KPI cards (units moved into the revenue hint) and the elasticities folded away.
    expect(expectKpiRowsAtMostFour(container)).toBe(4);
    expect(screen.queryByText("Unidades do cenário 12M")).not.toBeInTheDocument();
    expect(screen.getByText("Premissas do modelo").closest("details")).not.toHaveAttribute("open");
  });

  it("drops the prefill from the URL once another scenario is picked", async () => {
    mockApi(routes());
    const { location } = renderPage(
      <Scenarios />,
      "/app/scenarios",
      "/app/scenarios?customer=Litoral%20Market&distribution_change_pct=0.1",
    );
    await screen.findByText("Cenário pré-preenchido. Ajuste e salve se quiser mantê-lo.");
    fireEvent.click(screen.getByRole("button", { name: /Agressivo/ }));
    await waitFor(() => expect(location().search).toBe(""));
    expect(screen.queryByText(/Cenário pré-preenchido/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Nome")).toHaveValue("Agressivo");
  });

  it("has the goal allocation tab", async () => {
    const api = mockApi(routes());
    const { location } = renderPage(<Scenarios />, "/app/scenarios", "/app/scenarios");
    fireEvent.click(await screen.findByRole("button", { name: /Alocação de metas/ }));
    await waitFor(() => expect(api.count("POST /api/sop/allocation")).toBe(1));
    expect(location().search).toContain("tab=alocacao");
    expect(screen.queryByText(/Cenário pré-preenchido/)).not.toBeInTheDocument();
  });
});

describe("Modelos e FVA", () => {
  it("?tab=fva renders the FVA content as a tab", async () => {
    mockApi({ ...COMMON, "/api/fva": FVA });
    const { container } = renderPage(<ModelPerformance />, "/app/models", "/app/models?tab=fva");
    expect(await screen.findByTestId("fva-content")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Modelos e FVA" })).toBeInTheDocument();
    expect(screen.getByText("Escada do FVA")).toBeInTheDocument();
    expect(screen.getByText("+14,3 p.p.")).toBeInTheDocument();
    expect(screen.getByText("-12,6 p.p.")).toBeInTheDocument();
    // Dropped: monthly WMAPE lines and the best/worst example cards.
    expect(screen.queryByText("WMAPE mensal por etapa")).not.toBeInTheDocument();
    expect(screen.queryByText("Ajuste que mais destruiu valor")).not.toBeInTheDocument();
    expect(expectKpiRowsAtMostFour(container)).toBe(4);
  });

  it("FVA without historical adjustments says so instead of empty tables", async () => {
    mockApi({
      ...COMMON,
      "/api/fva": {
        ...FVA,
        stairstep: { ...FVA.stairstep, consensus: 0.148, fva_consensus_vs_statistical: 0 },
        summary: { overrides: 0 },
        by_planner: [],
        by_event_type: [],
        by_direction: [],
        by_magnitude: [],
        overrides: [],
      },
    });
    renderPage(<ModelPerformance />, "/app/models", "/app/models?tab=fva");
    expect(await screen.findByText("Sem histórico de ajustes comerciais")).toBeInTheDocument();
    expect(screen.getByText(/o consenso é igual ao estatístico/)).toBeInTheDocument();
    expect(screen.queryByText("Valor agregado por grupo")).not.toBeInTheDocument();
    expect(screen.queryByText("Log de ajustes")).not.toBeInTheDocument();
  });

  it("the Séries tab links each series to the workspace (keyboard reachable)", async () => {
    mockApi({
      ...COMMON,
      "/api/models/performance": [
        {
          series_id: SERIES_ID,
          customer: "Litoral Market",
          sku: "SKU-10101",
          product: "AquaViva Água Mineral 500ml",
          series_type: "Seasonal",
          champion: "Regression",
          wmape: 0.142,
          accuracy: 0.858,
          bias: -0.021,
          bias_class: "Balanced",
          challenger: "ETS",
          challenger_wmape: 0.161,
          gap_vs_challenger: 0.019,
          wmape_std: 0.03,
          confidence: "High",
          confidence_score: 82,
          history_months: 60,
        },
      ],
    });
    renderPage(<ModelPerformance />, "/app/models", "/app/models?tab=series");
    expect(await screen.findByRole("link", { name: /Abrir Litoral Market · SKU-10101/ })).toHaveAttribute(
      "href",
      "/app/forecasting?series=Litoral%20Market%7CSKU-10101",
    );
    expect(screen.getByText("1,9 p.p.")).toBeInTheDocument();
  });

  it("defaults to the ranking without the KPI row or the heatmaps tab", async () => {
    mockApi({
      ...COMMON,
      "/api/models/leaderboard": [
        { model: "Regression", wmape: 0.15, bias: 0.01, rmse: 10, rank: 2, champion_count: 85 },
        { model: "ARIMA", wmape: 0.12, bias: 0.0, rmse: 9, rank: 1, champion_count: 6 },
      ],
      "/api/models/distribution": {
        by_model: [{ model: "Regression", count: 85 }],
        by_family: [],
        by_type: [{ series_type: "Seasonal", champion: "Regression", count: 31 }],
        confidence: [],
      },
    });
    const { container } = renderPage(<ModelPerformance />, "/app/models", "/app/models");
    expect(
      await screen.findByText(
        "WMAPE de cada modelo medido apenas nas séries em que competiu — compare modelos dentro do mesmo padrão de demanda.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Modelo campeão por padrão de demanda")).toBeInTheDocument();
    expect(screen.queryByText("Mapas de calor")).not.toBeInTheDocument();
    expect(screen.queryByText("Distribuição de campeões")).not.toBeInTheDocument();
    expect(expectKpiRowsAtMostFour(container)).toBe(0);
    // Ordered by wins: Regression (85 séries) before ARIMA (6), whatever the WMAPE rank says.
    const rows = within(screen.getByText("Ranking de modelos").closest("section")!).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("Regressão");
    expect(rows[2]).toHaveTextContent("ARIMA");
  });
});

describe("Bases de dados", () => {
  const routes = (): Record<string, MockHandler> => ({
    ...COMMON,
    "/api/data/datasets": [DATASET],
    "/api/data/preview": { total: 0, rows: [] },
    "/api/data/active": DATASET,
  });

  it("has 2 tabs and links the upload to the Entrada", async () => {
    mockApi(routes());
    renderPage(<Data />, "/app/data", "/app/data");
    expect(await screen.findByRole("heading", { name: "Bases de dados" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Versões e prévia/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Diagnóstico$/ })).toBeInTheDocument();
    for (const gone of ["Carregar & diagnóstico", "Análise exploratória", "Perfil das séries"])
      expect(screen.queryByText(gone)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Carregar nova base/ })).toHaveAttribute(
      "href",
      "/app/entrada?acao=carregar",
    );
    expect(await screen.findByText("Versões da base")).toBeInTheDocument();
  });

  it("?tab=diagnostico shows the health report of the active base", async () => {
    mockApi(routes());
    renderPage(<Data />, "/app/data", "/app/data?tab=diagnostico");
    expect(await screen.findByText("Diagnóstico da base ativa: dataset_2026_10_v01")).toBeInTheDocument();
    expect(screen.getByText("Score de qualidade dos dados")).toBeInTheDocument();
  });
});

describe("Alertas", () => {
  it("links each alert type to the right deep-dive view", async () => {
    mockApi({ "/api/alerts": ALERTS });
    const { container } = renderPage(<Alerts />, "/app/alerts", "/app/alerts");
    const cards = await screen.findAllByRole("article");
    expect(cards).toHaveLength(4);
    const [highError, target, challenger, opportunity] = cards;

    const hrefOf = (card: HTMLElement) =>
      within(card)
        .getByRole("link", { name: /Investigar no deep dive/ })
        .getAttribute("href") ?? "";

    const h = hrefOf(highError);
    expect(h.startsWith("/app/desvios?")).toBe(true);
    expect(h).toContain("cmp=ac_fc");
    expect(h).toContain("customer=Atlas%20Hipermercados");
    expect(h).toContain("sku=SKU-30103");
    expect(h).toContain("nivel=series");
    expect(h).toContain("serie=Atlas%20Hipermercados%7CSKU-30103");

    const tg = hrefOf(target);
    expect(tg).toContain("cmp=fc_tg");
    expect(tg).toContain("customer=Litoral%20Market");
    expect(tg).toContain("nivel=category");

    const op = hrefOf(opportunity);
    expect(op.startsWith("/app/desvios?")).toBe(true);
    expect(op).not.toContain("cmp="); // fc_pl is the deep dive's default comparison
    expect(op).toContain("customer=ClickCesta");
    expect(op).toContain("nivel=category");

    expect(within(challenger).queryByRole("link", { name: /Investigar no deep dive/ })).toBeNull();
    expect(within(challenger).getByRole("link", { name: /Abrir no workspace de forecast/ })).toHaveAttribute(
      "href",
      "/app/forecasting?series=Rede%20Horizonte%20Supermercados%7CSKU-10201",
    );
    expectKpiRowsAtMostFour(container);
  });
});
