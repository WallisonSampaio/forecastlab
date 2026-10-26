/**
 * Stage 3 · Desvios (spec §2.3, package F5 acceptance).
 * Fixtures: `fixtures/deviations-*.json`, verbatim responses of the §4.3.3 endpoints on the seed-42 demo
 * (Litoral Market · SKU-30102 is a recurrent series: -23,0% vs orçamento in the last 12 months).
 */
import { configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { useNavigate } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { useFilters } from "../hooks/useFilters";
import { LENS_OF, type Cmp } from "../lib/deviationsUrl";
import Desvios, { PERIOD_RESET_NOTICE, SAVED_NOTICE } from "../pages/Desvios";
import type {
  DeviationExceptions,
  DeviationFocus,
  DeviationSeries,
  DeviationSummary,
} from "../types/deviations";
import exceptionsForecastFx from "./fixtures/deviations-exceptions-forecast.json";
import exceptionsPlanFx from "./fixtures/deviations-exceptions.json";
import focusForecastFx from "./fixtures/deviations-focus-forecast.json";
import focusPlanFx from "./fixtures/deviations-focus-plan.json";
import seriesForecastFx from "./fixtures/deviations-series-forecast.json";
import seriesPlanFx from "./fixtures/deviations-series.json";
import summaryForecastFx from "./fixtures/deviations-summary-forecast.json";
import summaryPlanFx from "./fixtures/deviations-summary-plan.json";
import { journeyFixture, mockApi, reply, type MockHandler, type MockRequest } from "./mockApi";
import { renderWithProviders } from "./render";

// The page renders 5 panels plus the drawer: give slow (shared) machines some room.
vi.setConfig({ testTimeout: 20_000 });
configure({ asyncUtilTimeout: 4_000 });

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

const clone = <T,>(v: unknown): T => structuredClone(v) as T;
const isForecast = (req: MockRequest) => LENS_OF[(req.params.get("cmp") ?? "fc_pl") as Cmp] === "previsao";

/** Fixture of the request's lens, echoing its `cmp` (as the backend does). */
function summaryFor(req: MockRequest): DeviationSummary {
  const s = clone<DeviationSummary>(isForecast(req) ? summaryForecastFx : summaryPlanFx);
  s.cmp = req.params.get("cmp") as Cmp;
  return s;
}
function focusFor(req: MockRequest): DeviationFocus {
  const f = clone<DeviationFocus>(isForecast(req) ? focusForecastFx : focusPlanFx);
  f.cmp = req.params.get("cmp") as Cmp;
  return f;
}
function exceptionsFor(req: MockRequest): DeviationExceptions {
  const e = clone<DeviationExceptions>(isForecast(req) ? exceptionsForecastFx : exceptionsPlanFx);
  const offset = Number(req.params.get("offset") ?? 0);
  if (offset > 0) {
    // Second page: the remaining rows (total - 15), with their own ids.
    const n = Math.max(0, Math.min(e.rows.length, e.total - offset));
    e.rows = e.rows.slice(0, n).map((r) => ({ ...r, series_id: `${r.series_id}-p2`, sku: `${r.sku}-p2` }));
  }
  return e;
}
function seriesFor(req: MockRequest): DeviationSeries {
  return clone<DeviationSeries>(isForecast(req) ? seriesForecastFx : seriesPlanFx);
}

function api(overrides: Record<string, MockHandler> = {}) {
  return mockApi({
    "/api/journey": journeyFixture("pronto"),
    "/api/deviations/summary": summaryFor,
    "/api/deviations/focus": focusFor,
    "/api/deviations/exceptions": exceptionsFor,
    "/api/deviations/series": seriesFor,
    ...overrides,
  });
}

/** Test-only control: browser Back. */
function BackButton() {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate(-1)}>
      historico-voltar
    </button>
  );
}

function renderDesvios(route = "/app/desvios") {
  return renderWithProviders(
    <>
      <Desvios />
      <BackButton />
    </>,
    { route, path: "/app/desvios" },
  );
}

const block = (id: string) => {
  const el = document.querySelector<HTMLElement>(`[data-visual="${id}"]`);
  if (!el) throw new Error(`bloco ${id} ausente`);
  return el;
};
const lastParams = (m: ReturnType<typeof api>, path: string) => {
  const reqs = m.requests(path);
  return Object.fromEntries(reqs[reqs.length - 1]?.params ?? []);
};
const PLAN_ROWS_LOADED = () => screen.findByRole("button", { name: "Detalhar Nordeste" });

describe("Desvios · URL state", () => {
  it("restores the full state from the URL on reload", async () => {
    const m = api();
    renderDesvios(
      "/app/desvios?cmp=fc_tg&periodo=t2&medida=units&region=Nordeste&nivel=customer" +
        "&sel=Litoral%20Market&serie=Litoral%20Market%7CSKU-30102&de=gap",
    );
    const drawer = await screen.findByRole("dialog", { name: /Litoral Market · SKU-30102/ });
    expect(drawer).toBeInTheDocument();
    await waitFor(() => expect(m.count("/api/deviations/series")).toBe(1));
    await waitFor(() => expect(m.count("/api/deviations/exceptions")).toBe(1));

    expect(lastParams(m, "/api/deviations/summary")).toMatchObject({
      cmp: "fc_tg",
      period: "t2",
      measure: "units",
      level: "customer",
      region: "Nordeste",
    });
    expect(lastParams(m, "/api/deviations/focus")).toMatchObject({
      cmp: "fc_tg",
      focus_level: "customer",
      focus: "Litoral Market",
      region: "Nordeste",
    });
    expect(lastParams(m, "/api/deviations/exceptions")).toMatchObject({
      focus_level: "customer",
      focus: "Litoral Market",
      direction: "adverse",
      limit: "15",
      offset: "0",
    });
    expect(lastParams(m, "/api/deviations/series")).toMatchObject({
      series_id: "Litoral Market|SKU-30102",
      cmp: "fc_tg",
      period: "t2",
      measure: "units",
    });

    await waitFor(() => expect(screen.getByLabelText("Período")).toHaveValue("t2"));
    expect(screen.getByLabelText("Comparação")).toHaveValue("fc_tg");
    expect(screen.getByLabelText("Agrupar por")).toHaveValue("customer");
    expect(screen.getByText("Região: Nordeste")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Voltar ao relatório · Gap vs orçamento/ })).toBeInTheDocument();
  });

  it("first load makes 3 deviation requests (summary, focus, exceptions)", async () => {
    const m = api();
    renderDesvios();
    await PLAN_ROWS_LOADED();
    await waitFor(() => expect(m.count("/api/deviations/exceptions")).toBe(1));
    expect(m.count("/api/deviations/summary")).toBe(1);
    expect(m.count("/api/deviations/focus")).toBe(1);
    expect(m.count("/api/deviations/series")).toBe(0);
  });

  it("row click sets sel; focus and exceptions requests carry focus_level and focus", async () => {
    const m = api();
    const { location } = renderDesvios();
    await PLAN_ROWS_LOADED();
    const row = within(block("onde")).getByRole("button", { name: /^Nordeste/ });
    expect(row).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(row);

    await waitFor(() => expect(location().search).toContain("sel=Nordeste"));
    await waitFor(() =>
      expect(lastParams(m, "/api/deviations/focus")).toMatchObject({
        focus_level: "region",
        focus: "Nordeste",
      }),
    );
    await waitFor(() =>
      expect(lastParams(m, "/api/deviations/exceptions")).toMatchObject({
        focus_level: "region",
        focus: "Nordeste",
      }),
    );
    expect(within(block("onde")).getByRole("button", { name: /^Nordeste/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("› drills (path + next level, push) and browser Back restores the previous level", async () => {
    const m = api();
    const { location } = renderDesvios();
    await PLAN_ROWS_LOADED();
    // `sel` replaces the current entry…
    fireEvent.click(within(block("onde")).getByRole("button", { name: /^Sul/ }));
    await waitFor(() => expect(location().search).toContain("sel=Sul"));
    // …a drill pushes a new one.
    fireEvent.click(within(block("onde")).getByRole("button", { name: "Detalhar Nordeste" }));
    await waitFor(() => expect(location().search).toBe("?region=Nordeste"));
    await waitFor(() =>
      expect(lastParams(m, "/api/deviations/summary")).toMatchObject({
        region: "Nordeste",
        level: "channel",
      }),
    );
    expect(screen.getByText("Região: Nordeste")).toBeInTheDocument();

    fireEvent.click(screen.getByText("historico-voltar"));
    await waitFor(() => expect(location().search).toBe("?sel=Sul"));
    await waitFor(() => expect(lastParams(m, "/api/deviations/summary")).toMatchObject({ level: "region" }));
    expect(lastParams(m, "/api/deviations/summary")).not.toHaveProperty("region");
  });

  it("breadcrumb × removes the dimension and every later one", async () => {
    api();
    const { location } = renderDesvios(
      "/app/desvios?region=Nordeste&channel=Varejo%20Moderno&customer=Litoral%20Market",
    );
    const nav = await screen.findByRole("navigation", { name: "Recorte" });
    fireEvent.click(within(nav).getByRole("button", { name: "Remover Canal: Varejo Moderno" }));
    await waitFor(() => expect(location().search).toBe("?region=Nordeste"));

    fireEvent.click(within(nav).getByRole("button", { name: "Empresa toda" }));
    await waitFor(() => expect(location().search).toBe(""));
  });

  it("a month click sets periodo", async () => {
    const m = api();
    const { location } = renderDesvios();
    const quando = block("quando");
    fireEvent.click(await within(quando).findByRole("button", { name: /Ver tabela/ }));
    fireEvent.click(within(quando).getByRole("button", { name: "dez/2026" }));
    await waitFor(() => expect(location().search).toBe("?periodo=2026-12"));
    await waitFor(() =>
      expect(lastParams(m, "/api/deviations/summary")).toMatchObject({ period: "2026-12" }),
    );
  });

  it("while the drilled level loads, the previous level's rows neither drill nor select", async () => {
    let release = () => {};
    const gate = new Promise<void>((r) => (release = r));
    api({
      "/api/deviations/summary": async (req: MockRequest) => {
        if (req.params.get("region")) await gate;
        return summaryFor(req);
      },
    });
    const { location } = renderDesvios();
    await PLAN_ROWS_LOADED();
    fireEvent.click(within(block("onde")).getByRole("button", { name: "Detalhar Nordeste" }));
    await waitFor(() => expect(location().search).toBe("?region=Nordeste"));
    // The region rows stay on screen (dimmed) until the channel breakdown arrives: a "›" or a click
    // on them must not write a region name into the channel level.
    fireEvent.click(within(block("onde")).getByRole("button", { name: "Detalhar Sul" }));
    fireEvent.click(within(block("onde")).getByRole("button", { name: /^Sul/ }));
    expect(location().search).toBe("?region=Nordeste");
    release();
  });

  it("switching the lens resets cmp, periodo and sel (keeps the path)", async () => {
    api();
    const { location } = renderDesvios("/app/desvios?periodo=t2&region=Sul&sel=Varejo%20Moderno");
    const lens = await screen.findByRole("group", { name: "Lente" });
    fireEvent.click(within(lens).getByRole("button", { name: "Previsão" }));
    await waitFor(() => expect(location().search).toBe("?lente=previsao&cmp=ac_fc&region=Sul"));
    expect(within(lens).getByRole("button", { name: "Previsão" })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("Desvios · layout", () => {
  it("has exactly 5 data-visual blocks with questions, ≤ 4 KPI cards and pt-BR copy", async () => {
    api();
    renderDesvios();
    await PLAN_ROWS_LOADED();
    await screen.findByText("Desvio vs orçamento");
    await waitFor(() => expect(screen.getAllByText(/Mostrando 15 de 26/).length).toBe(1));

    const blocks = Array.from(document.querySelectorAll<HTMLElement>("[data-visual]"));
    expect(blocks.map((b) => b.dataset.visual)).toEqual(["kpis", "onde", "porque", "quando", "excecoes"]);
    for (const b of blocks) expect(b.dataset.question?.trim()).toBeTruthy();
    expect(block("kpis").querySelectorAll(":scope > .card")).toHaveLength(4);

    // H1 = backend headline; panel titles are questions.
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(summaryPlanFx.headline);
    for (const q of [
      "Onde está o desvio?",
      "Por que desviou?",
      "Quando aconteceu?",
      "Quais séries tratar primeiro?",
    ])
      expect(screen.getByRole("heading", { name: q })).toBeInTheDocument();

    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\b(Budget|Target|Forecast error|Loading|Error|Next|Previous|Revenue)\b/);
  });

  it("Plano columns include the chance of reaching the budget; Previsão shows the forecast columns", async () => {
    api();
    renderDesvios();
    const table = await within(block("excecoes")).findByRole("table");
    const heads = within(table)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(heads).toEqual(["Série", "Desvio (R$)", "Chance", "Causa", "Ação recomendada", "Ações"]);
  });

  it("shows the JourneyGate (and makes no deviation request) before the run completes", async () => {
    const m = api({ "/api/journey": journeyFixture("running") });
    renderDesvios();
    expect(await screen.findByText("Antes do relatório, a confiança")).toBeInTheDocument();
    expect(m.count("/api/deviations/summary")).toBe(0);
    expect(m.count("/api/deviations/exceptions")).toBe(0);
  });
});

describe("Desvios · exceptions table", () => {
  it("'Ver mais' appends the next 15; the Perdas/Ganhos toggle restarts the list", async () => {
    const m = api();
    renderDesvios();
    const card = block("excecoes");
    const table = await within(card).findByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(16); // header + 15

    fireEvent.click(within(card).getByRole("button", { name: /Ver mais/ }));
    await waitFor(() => expect(within(card).getAllByRole("row")).toHaveLength(27)); // header + 26
    expect(lastParams(m, "/api/deviations/exceptions")).toMatchObject({ offset: "15", limit: "15" });
    expect(within(card).queryByRole("button", { name: /Ver mais/ })).not.toBeInTheDocument();
    expect(within(card).getByText(/Mostrando 26 de 26/)).toBeInTheDocument();

    fireEvent.click(within(card).getByRole("tab", { name: "Ganhos" }));
    await waitFor(() =>
      expect(lastParams(m, "/api/deviations/exceptions")).toMatchObject({
        direction: "favorable",
        offset: "0",
      }),
    );
    await waitFor(() => expect(within(card).getAllByRole("row")).toHaveLength(16));
  });

  it("row 'Ações' menu opens the series card", async () => {
    api();
    const { location } = renderDesvios();
    const card = block("excecoes");
    await within(card).findByRole("table");
    const first = exceptionsPlanFx.rows[0];
    fireEvent.click(
      within(card).getByRole("button", { name: `Ações para ${first.customer} · ${first.sku}` }),
    );
    const menu = await screen.findByRole("menu");
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .map((b) => b.textContent),
    ).toEqual(["Abrir ficha", "Criar ajuste comercial", "Simular cenário", "Perguntar à IA"]);
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Abrir ficha" }));
    await waitFor(() => expect(new URLSearchParams(location().search).get("serie")).toBe(first.series_id));
    expect(await screen.findByRole("dialog", { name: new RegExp(first.customer) })).toBeInTheDocument();
  });

  it("switching the lens never shows plan rows under the forecast columns", async () => {
    let release = () => {};
    const gate = new Promise<void>((r) => (release = r));
    api({
      "/api/deviations/exceptions": async (req: MockRequest) => {
        if (isForecast(req)) await gate;
        return exceptionsFor(req);
      },
    });
    renderDesvios();
    await within(block("excecoes")).findByRole("table");
    const lens = await screen.findByRole("group", { name: "Lente" });
    fireEvent.click(within(lens).getByRole("button", { name: "Previsão" }));
    await waitFor(() => expect(within(block("excecoes")).queryByRole("table")).not.toBeInTheDocument());
    release();
    const table = await within(block("excecoes")).findByRole("table");
    expect(within(table).getAllByRole("columnheader")[1]).toHaveTextContent("Erro (R$)");
  });

  it("the cause chip keeps its name when the focus no longer lists that cause", async () => {
    api({
      "/api/deviations/focus": (req: MockRequest) => ({ ...focusFor(req), causes: [] }),
    });
    renderDesvios("/app/desvios?lente=previsao&cmp=ac_fc&causa=volatilidade");
    expect(
      await within(block("excecoes")).findByText(/Causa: Demanda intermitente ou volátil/),
    ).toBeInTheDocument();
  });

  it("Previsão: a cause click filters the table and its chip × clears it", async () => {
    const m = api();
    const { location } = renderDesvios("/app/desvios?lente=previsao&cmp=ac_fc");
    const why = block("porque");
    const cause = await within(why).findByRole("button", { name: /^Promoção não antecipada/ });
    fireEvent.click(cause);
    await waitFor(() => expect(new URLSearchParams(location().search).get("causa")).toBe("promocao"));
    await waitFor(() =>
      expect(lastParams(m, "/api/deviations/exceptions")).toMatchObject({ cause: "promocao" }),
    );

    const card = block("excecoes");
    expect(within(card).getByText(/Causa: Promoção não antecipada/)).toBeInTheDocument();
    const heads = within(card)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(heads).toEqual(["Série", "Erro (R$)", "Viés", "Causa principal", "Ação recomendada", "Ações"]);
    fireEvent.click(
      within(card).getByRole("button", { name: "Remover filtro Causa: Promoção não antecipada" }),
    );
    await waitFor(() => expect(new URLSearchParams(location().search).get("causa")).toBeNull());
  });
});

describe("Desvios · actions", () => {
  it("'Perguntar à IA' copies the drill path into useFilters and asks the backend question", async () => {
    api();
    const { location } = renderDesvios("/app/desvios?region=Nordeste");
    const ask = (await screen.findAllByRole("button", { name: "Perguntar à IA" }))[0];
    await waitFor(() => expect(ask).toBeEnabled());
    fireEvent.click(ask);

    const question = focusPlanFx.actions.find((a) => a.kind === "ask_ai")!.prefill!.question as string;
    await waitFor(() => expect(location().pathname).toBe("/app/ai"));
    expect(location().search).toBe(`?q=${encodeURIComponent(question)}`);
    expect(useFilters.getState().filters).toEqual({ region: "Nordeste" });
  });

  it("'Criar ajuste' opens the prefilled modal, posts /api/overrides and invalidates the queries", async () => {
    const series = clone<DeviationSeries>(seriesPlanFx);
    const prefill = {
      customer: "Litoral Market",
      sku: "SKU-30102",
      date: "2026-12-01",
      event_type: "Promoção",
      uplift_pct: 0.2,
      comment: "Sugerido pelo deep dive: promoção não antecipada em dez/2025",
    };
    series.actions = series.actions.map((a) => (a.kind === "create_override" ? { ...a, prefill } : a));
    const horizon = summaryPlanFx.period.months;
    const m = api({
      "/api/deviations/series": series,
      "/api/data/dimensions": { horizon, last_actual: "2026-09-01" },
      "/api/overrides/event-library": [
        { type: "Promoção", typical_uplift: 0.15, description: "Ação promocional" },
        { type: "Merchandising", typical_uplift: 0.12, description: "Ponto extra" },
      ],
      "POST /api/overrides": { id: "OVR-1" },
    });
    renderDesvios("/app/desvios?serie=Litoral%20Market%7CSKU-30102");
    const drawer = await screen.findByRole("dialog", { name: /Litoral Market · SKU-30102/ });
    fireEvent.click(await within(drawer).findByRole("button", { name: "Criar ajuste comercial" }));

    const modal = await screen.findByRole("dialog", { name: "Criar ajuste comercial" });
    const add = await within(modal).findByRole("button", { name: /Adicionar ajuste/ });
    await waitFor(() => expect(within(modal).getByLabelText(/^Evento/)).toHaveValue("Promoção"));
    expect(within(modal).getByLabelText("Mês")).toHaveValue("2026-12-01");
    expect(within(modal).getByLabelText("Uplift esperado (%)")).toHaveValue("20");
    expect(within(modal).getByLabelText("Comentário")).toHaveValue(prefill.comment);

    const before = m.count("/api/deviations/summary");
    fireEvent.click(add);
    await waitFor(() => expect(m.count("POST /api/overrides")).toBe(1));
    expect(m.requests("/api/overrides").find((r) => r.method === "POST")!.body).toMatchObject({
      customer: "Litoral Market",
      sku: "SKU-30102",
      date: "2026-12-01",
      event_type: "Promoção",
      uplift_pct: 0.2,
      comment: prefill.comment,
    });
    expect(await screen.findByText(SAVED_NOTICE)).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Criar ajuste comercial" })).not.toBeInTheDocument();
    await waitFor(() => expect(m.count("/api/deviations/summary")).toBeGreaterThan(before));
  });

  it("'Simular cenário' from the drawer goes to Cenários with the series scope", async () => {
    api();
    const { location } = renderDesvios("/app/desvios?region=Nordeste&serie=Litoral%20Market%7CSKU-30102");
    const drawer = await screen.findByRole("dialog", { name: /Litoral Market · SKU-30102/ });
    fireEvent.click(await within(drawer).findByRole("button", { name: "Simular cenário" }));
    await waitFor(() => expect(location().pathname).toBe("/app/scenarios"));
    expect(location().search).toBe("?customer=Litoral%20Market&sku=SKU-30102");
    expect(useFilters.getState().filters).toEqual({
      region: "Nordeste",
      customer: "Litoral Market",
      sku: "SKU-30102",
    });
  });
});

describe("Desvios · series card", () => {
  it("shows the header values, the recurrence line and the plan evidence", async () => {
    api();
    renderDesvios("/app/desvios?serie=Litoral%20Market%7CSKU-30102");
    const drawer = await screen.findByRole("dialog", { name: /Litoral Market · SKU-30102/ });
    expect(await within(drawer).findByText("Últimos 12 meses: -23,0% vs orçamento")).toBeInTheDocument();
    expect(within(drawer).getByText("Evidências")).toBeInTheDocument();
    expect(within(drawer).getByText(/Ponte da série:/)).toBeInTheDocument();
    expect(within(drawer).getByText(seriesPlanFx.recommended_action.label)).toBeInTheDocument();
    expect(
      within(drawer)
        .getAllByRole("button")
        .map((b) => b.textContent),
    ).toEqual(
      expect.arrayContaining([
        "Abrir no workspace",
        "Criar ajuste comercial",
        "Simular cenário",
        "Perguntar à IA",
      ]),
    );
  });

  it("Previsão: one evidence row per backtest month, without the recurrence line", async () => {
    api();
    renderDesvios("/app/desvios?lente=previsao&cmp=ac_fc&serie=Litoral%20Market%7CSKU-30102");
    const drawer = await screen.findByRole("dialog", { name: /Litoral Market · SKU-30102/ });
    const table = await within(drawer).findByRole("table", { name: "Evidências por mês de backtest" });
    expect(within(table).getAllByRole("row")).toHaveLength(seriesForecastFx.evidence.length + 1);
    expect(within(drawer).queryByText(/Últimos 12 meses/)).not.toBeInTheDocument();
  });

  it("closing the card removes `serie` from the URL", async () => {
    api();
    const { location } = renderDesvios("/app/desvios?serie=Litoral%20Market%7CSKU-30102");
    const drawer = await screen.findByRole("dialog", { name: /Litoral Market · SKU-30102/ });
    fireEvent.click(within(drawer).getByRole("button", { name: "Fechar" }));
    await waitFor(() => expect(location().search).toBe(""));
  });
});

describe("Desvios · edge states", () => {
  it("summary.available === false: EmptyState with the reason and a reset to the lens default", async () => {
    const unavailable = (req: MockRequest) => {
      const s = summaryFor(req);
      s.comparisons = s.comparisons.map((c) =>
        c.cmp === "ac_cs"
          ? { ...c, available: false, reason: "Sem histórico de ajustes comerciais nesta base." }
          : c,
      );
      if (s.cmp === "ac_cs")
        Object.assign(s, {
          available: false,
          reason: "Sem histórico de ajustes comerciais nesta base.",
          kpis: [],
          headline: "",
        });
      return s;
    };
    api({ "/api/deviations/summary": unavailable });
    const { location } = renderDesvios("/app/desvios?lente=previsao&cmp=ac_cs");
    expect(await screen.findByText("Sem histórico de ajustes comerciais nesta base.")).toBeInTheDocument();
    expect(document.querySelectorAll("[data-visual]")).toHaveLength(0);
    const option = within(screen.getByLabelText("Comparação")).getByRole("option", {
      name: /Real × Consenso histórico \(com ajustes\) — sem histórico de ajustes/,
    });
    expect(option).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Ver Real × Estatístico \(campeão\)/ }));
    await waitFor(() => expect(location().search).toBe("?lente=previsao&cmp=ac_fc"));
  });

  it("a period without plan rows offers 'Voltar ao período padrão'", async () => {
    const noPlanMonth = (req: MockRequest) => {
      const s = summaryFor(req);
      if (req.params.get("period") === "2027-09")
        Object.assign(s, {
          available: false,
          reason: "Não há orçamento/meta para este período.",
          kpis: [],
          headline: "",
        });
      return s;
    };
    api({ "/api/deviations/summary": noPlanMonth });
    const { location } = renderDesvios("/app/desvios?periodo=2027-09");
    expect(await screen.findByText("Não há orçamento/meta para este período.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Voltar ao período padrão" }));
    await waitFor(() => expect(location().search).toBe(""));
  });

  it("a path with no series: 'Nenhuma série neste recorte' and back to Empresa toda", async () => {
    const empty = (req: MockRequest) => {
      const s = summaryFor(req);
      if (req.params.get("region") === "Inexistente")
        Object.assign(s, {
          available: false,
          reason: "Nenhuma série neste recorte.",
          kpis: [],
          headline: "",
          node: { label: "Inexistente", path: [], n_series: 0 },
        });
      return s;
    };
    api({ "/api/deviations/summary": empty });
    const { location } = renderDesvios("/app/desvios?region=Inexistente");
    expect(await screen.findByText("Nenhuma série neste recorte")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Voltar para Empresa toda" }));
    await waitFor(() => expect(location().search).toBe(""));
  });

  it("a month outside the window (HTTP 400) resets periodo with a notice", async () => {
    const rejecting =
      (ok: (req: MockRequest) => unknown) =>
      (req: MockRequest): unknown =>
        req.params.get("period") === "2020-01"
          ? reply(400, { detail: "Período inválido para esta comparação." })
          : ok(req);
    api({
      "/api/deviations/summary": rejecting(summaryFor),
      "/api/deviations/focus": rejecting(focusFor),
      "/api/deviations/exceptions": rejecting(exceptionsFor),
    });
    const { location } = renderDesvios("/app/desvios?periodo=2020-01");
    await waitFor(() => expect(location().search).toBe(""));
    expect(await screen.findByText(PERIOD_RESET_NOTICE)).toBeInTheDocument();
  });

  it("without plan rows the Plano lens is disabled and the default comparison becomes ac_fc", async () => {
    const noPlan = (req: MockRequest) => {
      const s = summaryFor(req);
      s.comparisons = s.comparisons.map((c) =>
        LENS_OF[c.cmp] === "plano"
          ? { ...c, available: false, reason: "Não há orçamento/meta nesta base." }
          : c,
      );
      if (!isForecast(req))
        Object.assign(s, { available: false, reason: "Não há orçamento/meta nesta base.", kpis: [] });
      return s;
    };
    api({ "/api/deviations/summary": noPlan });
    const { location } = renderDesvios();
    await waitFor(() => expect(location().search).toBe("?lente=previsao&cmp=ac_fc"));
    const plano = within(await screen.findByRole("group", { name: "Lente" })).getByRole("button", {
      name: "Plano",
    });
    await waitFor(() => expect(plano).toBeDisabled());
    expect(plano).toHaveAttribute("title", "Sem orçamento/meta nesta base");
    await waitFor(() =>
      expect(
        within(screen.getByLabelText("Comparação")).getByRole("option", {
          name: /Consenso × Orçamento · próximos 12 meses — sem orçamento nesta base/,
        }),
      ).toBeDisabled(),
    );
  });

  it("renders the backend notices as chips", async () => {
    const withNotice = (req: MockRequest) => {
      const s = summaryFor(req);
      s.notices = ["Orçamento estimado automaticamente — desvios ilustrativos"];
      return s;
    };
    api({ "/api/deviations/summary": withNotice });
    renderDesvios();
    const list = await screen.findByRole("list", { name: "Avisos sobre os dados" });
    expect(within(list).getByText(/Orçamento estimado automaticamente/)).toBeInTheDocument();
  });
});
