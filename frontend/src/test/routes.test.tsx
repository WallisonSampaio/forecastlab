/**
 * F1 · shell, navigation and routing contracts (spec §1, §5 F1 acceptance).
 * Pages are stubbed so these tests exercise only the router, the shell and the journey components.
 */
import { act, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { JourneyGate } from "../components/journey/JourneyGate";
import { GOV_STORAGE_KEY, LOCKED_HINT } from "../components/journey/JourneyNav";
import { RerunBanner } from "../components/journey/RerunBanner";
import { ExportMenu } from "../components/RunControls";
import { useGet } from "../hooks/useApi";
import { JOURNEY_KEY, runProgressLine, useJourney } from "../hooks/useJourney";
import {
  chapterOrDefault,
  loadReportScope,
  mergeSearch,
  REPORT_SCOPE_STORAGE_KEY,
  reportScopeFromSearch,
  ROUTES,
  saveReportScope,
  sectionKey,
} from "../lib/routes";
import { journeyFixture, mockApi, shellRoutes } from "./mockApi";
import { renderWithProviders } from "./render";

const h = vi.hoisted(() => ({
  mounts: { relatorio: 0 },
  stub: (title: string) => async () => {
    const { createElement } = await import("react");
    return { default: () => createElement("h1", null, title) };
  },
}));

vi.mock("../pages/Entrada", h.stub("Página Entrada"));
vi.mock("../pages/Desvios", h.stub("Página Desvios"));
vi.mock("../pages/ModelPerformance", h.stub("Página Modelos"));
vi.mock("../pages/Data", h.stub("Página Bases"));
vi.mock("../pages/Forecasting", h.stub("Página Workspace"));
vi.mock("../pages/Scenarios", h.stub("Página Cenários"));
vi.mock("../pages/AIAnalyst", h.stub("Página IA"));
vi.mock("../pages/Alerts", h.stub("Página Alertas"));
vi.mock("../pages/Relatorio", async () => {
  const React = await import("react");
  const { Link, useParams } = await import("react-router-dom");
  function RelatorioStub() {
    const { capitulo } = useParams();
    React.useEffect(() => {
      h.mounts.relatorio += 1;
    }, []);
    return React.createElement(
      "div",
      null,
      React.createElement("h1", null, `Relatório ${capitulo}`),
      React.createElement(Link, { to: "/app/relatorio/realizado" }, "Próximo capítulo"),
      React.createElement(Link, { to: "/app/desvios" }, "Investigar"),
    );
  }
  return { default: RelatorioStub };
});

// Whole-App renders are slow under a parallel suite run (jsdom + first render of the shell).
configure({ asyncUtilTimeout: 5000 });
vi.setConfig({ testTimeout: 20_000 });

beforeAll(async () => {
  // Load the (stubbed) lazy pages once, so the first routing test does not pay the module load.
  await Promise.all([
    import("../pages/Entrada"),
    import("../pages/Relatorio"),
    import("../pages/Desvios"),
    import("../pages/ModelPerformance"),
  ]);
});

beforeEach(() => {
  h.mounts.relatorio = 0;
  localStorage.clear();
  sessionStorage.clear();
});

/** Renders the whole App at `route` with the shell's requests mocked. */
function renderApp(route: string, journey = journeyFixture("pronto"), alerts = {}) {
  const api = mockApi(shellRoutes(journey, alerts));
  return { api, ...renderWithProviders(undefined, { route }) };
}

const path = (loc: { pathname: string; search: string }) => `${loc.pathname}${loc.search}`;

/* ---------------------------------------------------------------------------- redirects */

describe("routes and redirects (spec §1.3)", () => {
  it.each([
    ["/app", "/app/entrada", "Página Entrada"],
    ["/app/overview?region=Sul", "/app/relatorio/resumo?region=Sul", "Relatório resumo"],
    ["/app/sop", "/app/relatorio/meta", "Relatório meta"],
    ["/app/fva", "/app/models?tab=fva", "Página Modelos"],
    ["/app/fva?region=Sul", "/app/models?tab=fva&region=Sul", "Página Modelos"],
    ["/app/relatorio/xyz", "/app/relatorio/resumo", "Relatório resumo"],
    ["/app/relatorio/xyz?channel=Atacado", "/app/relatorio/resumo?channel=Atacado", "Relatório resumo"],
    ["/app/relatorio?region=Sul", "/app/relatorio/resumo?region=Sul", "Relatório resumo"],
    ["/app/settings", "/app/entrada", "Página Entrada"],
    ["/app/desvios?cmp=ac_fc", "/app/desvios?cmp=ac_fc", "Página Desvios"],
  ])("%s -> %s", async (from, to, heading) => {
    const { location } = renderApp(from);
    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
    expect(path(location())).toBe(to);
  });

  it("an unknown path goes to the home page", async () => {
    mockApi({ "/api/overview": { has_run: false, n_series: 220 }, "/api/meta": { models: [] } });
    const { location } = renderWithProviders(undefined, { route: "/qualquer/coisa" });
    await waitFor(() => expect(location().pathname).toBe("/"));
  });

  it("changing chapters keeps the report mounted (Outlet key = first two path segments)", async () => {
    const { location } = renderApp("/app/relatorio/resumo");
    expect(await screen.findByRole("heading", { name: "Relatório resumo" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "Próximo capítulo" }));
    expect(await screen.findByRole("heading", { name: "Relatório realizado" })).toBeInTheDocument();
    expect(location().pathname).toBe("/app/relatorio/realizado");
    expect(h.mounts.relatorio).toBe(1);
  });

  it("sectionKey keeps the first two path segments", () => {
    expect(sectionKey("/app/relatorio/resumo")).toBe("/app/relatorio");
    expect(sectionKey("/app/relatorio/gap")).toBe("/app/relatorio");
    expect(sectionKey("/app/desvios")).toBe("/app/desvios");
    expect(sectionKey("/app")).toBe("/app");
  });

  it("chapterOrDefault sends unknown chapters to resumo", () => {
    expect(chapterOrDefault("gap")).toBe("gap");
    expect(chapterOrDefault("xyz")).toBe("resumo");
    expect(chapterOrDefault(undefined)).toBe("resumo");
  });
});

/* ------------------------------------------------------------------------------- builders */

describe("route builders", () => {
  it("ROUTES builds the journey and tool links", () => {
    expect(ROUTES.entrada()).toBe("/app/entrada");
    expect(ROUTES.entrada({ acao: "carregar" })).toBe("/app/entrada?acao=carregar");
    expect(ROUTES.relatorio()).toBe("/app/relatorio/resumo");
    expect(ROUTES.relatorio("gap", { channel: "Varejo Moderno" })).toBe(
      "/app/relatorio/gap?channel=Varejo%20Moderno",
    );
    expect(ROUTES.desvios({ cmp: "ac_fc" })).toBe("/app/desvios?lente=previsao&cmp=ac_fc");
    expect(ROUTES.workspace("Litoral Market|SKU-10101")).toBe(
      "/app/forecasting?series=Litoral%20Market%7CSKU-10101",
    );
    expect(ROUTES.workspace("A|B", { mes: "2026-12-01", evento: "Promoção", uplift: 0.2 })).toBe(
      "/app/forecasting?series=A%7CB&ajuste=1&mes=2026-12-01&evento=Promo%C3%A7%C3%A3o&uplift=0.2",
    );
    expect(ROUTES.cenarios({ customer: "Litoral Market", distribution_change_pct: 0.1 })).toBe(
      "/app/scenarios?customer=Litoral%20Market&distribution_change_pct=0.1",
    );
    expect(ROUTES.ia("A meta é realista?")).toBe("/app/ai?q=A%20meta%20%C3%A9%20realista%3F");
    expect(ROUTES.modelos("fva")).toBe("/app/models?tab=fva");
    expect(ROUTES.modelos()).toBe("/app/models");
    expect(ROUTES.bases("diagnostico")).toBe("/app/data?tab=diagnostico");
    expect(ROUTES.alertas()).toBe("/app/alerts");
  });

  it("mergeSearch appends the current query and lets the target win", () => {
    expect(mergeSearch("/app/relatorio/resumo", "?region=Sul")).toBe("/app/relatorio/resumo?region=Sul");
    expect(mergeSearch("/app/relatorio/resumo", "")).toBe("/app/relatorio/resumo");
    expect(mergeSearch("/app/models?tab=fva", "?region=Rede%20Sul&tab=ranking")).toBe(
      "/app/models?tab=fva&region=Rede%20Sul",
    );
    // A malformed escape typed by hand never breaks the redirect.
    expect(mergeSearch("/app/models?tab=fva", "?%E0%A4=1")).toBe("/app/models?tab=fva&%E0%A4=1");
  });

  it("report scope: one dimension from the URL, kept in sessionStorage", () => {
    expect(reportScopeFromSearch(new URLSearchParams("channel=Atacado&region=Sul"))).toEqual({
      region: "Sul",
    });
    expect(reportScopeFromSearch(new URLSearchParams("customer=X"))).toEqual({});
    saveReportScope({ category: "Bebidas" });
    expect(JSON.parse(sessionStorage.getItem(REPORT_SCOPE_STORAGE_KEY) ?? "{}")).toEqual({
      category: "Bebidas",
    });
    expect(loadReportScope()).toEqual({ category: "Bebidas" });
    saveReportScope({});
    expect(loadReportScope()).toEqual({});
    sessionStorage.setItem(REPORT_SCOPE_STORAGE_KEY, "{corrompido");
    expect(loadReportScope()).toEqual({});
  });
});

/* ------------------------------------------------------------------------------------ nav */

describe("sidebar (spec §1.2)", () => {
  it("renders the groups Jornada (3), Ferramentas (4) and Governança (2)", async () => {
    renderApp("/app/entrada");
    const jornada = await screen.findByRole("group", { name: "Jornada" });
    expect(
      within(jornada)
        .getAllByRole("link")
        .map((a) => a.getAttribute("href")),
    ).toEqual(["/app/entrada", "/app/relatorio/resumo", "/app/desvios"]);
    const ferramentas = screen.getByRole("group", { name: "Ferramentas" });
    expect(
      within(ferramentas)
        .getAllByRole("link")
        .map((a) => a.getAttribute("href")),
    ).toEqual(["/app/forecasting", "/app/scenarios", "/app/alerts", "/app/ai"]);
    const governanca = screen.getByRole("group", { name: "Governança" });
    expect(within(governanca).queryAllByRole("link")).toHaveLength(0); // collapsed by default
    fireEvent.click(screen.getByRole("button", { name: "Governança" }));
    expect(
      within(governanca)
        .getAllByRole("link")
        .map((a) => a.textContent),
    ).toEqual(["Modelos e FVA", "Bases de dados"]);
  });

  it("the Governança state survives a reload (localStorage fl.nav.gov)", async () => {
    const first = renderApp("/app/entrada");
    const toggle = await screen.findByRole("button", { name: "Governança" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(localStorage.getItem(GOV_STORAGE_KEY)).toBe("1");
    first.unmount();

    const second = renderApp("/app/entrada");
    const again = await screen.findByRole("button", { name: "Governança" });
    expect(again).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Modelos e FVA" })).toBeInTheDocument();
    fireEvent.click(again);
    expect(localStorage.getItem(GOV_STORAGE_KEY)).toBe("0");
    second.unmount();

    renderApp("/app/entrada");
    expect(await screen.findByRole("button", { name: "Governança" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("opens Governança on its own pages and marks the active link", async () => {
    renderApp("/app/models?tab=fva");
    expect(await screen.findByRole("heading", { name: "Página Modelos" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Modelos e FVA" })).toHaveAttribute("aria-current", "page");
  });

  it("'Relatório executivo' is active on every chapter and keeps the saved report scope", async () => {
    saveReportScope({ region: "Sul" });
    renderApp("/app/relatorio/gap?region=Sul");
    const link = await screen.findByRole("link", { name: "Relatório executivo" });
    expect(link).toHaveAttribute("aria-current", "page");
    expect(link).toHaveAttribute("href", "/app/relatorio/resumo?region=Sul");
    expect(screen.getByRole("link", { name: "Entrada · dados e modelos" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("on the report, the 'Relatório executivo' link follows the URL scope (not a stale session value)", async () => {
    saveReportScope({ region: "Sul" });
    renderApp("/app/relatorio/gap?channel=Atacado");
    expect(await screen.findByRole("link", { name: "Relatório executivo" })).toHaveAttribute(
      "href",
      "/app/relatorio/resumo?channel=Atacado",
    );
  });

  it("locks Relatório and Desvios until the run completes (still links, with a hint)", async () => {
    renderApp("/app/entrada", journeyFixture("running"));
    const report = await screen.findByRole("link", { name: "Relatório executivo" });
    await waitFor(() => expect(report).toHaveAttribute("data-locked", "true"));
    expect(report).toHaveAccessibleDescription(LOCKED_HINT);
    expect(screen.getByRole("link", { name: "Desvios" })).toHaveAccessibleDescription(LOCKED_HINT);
    const entrada = screen.getByRole("link", { name: "Entrada · dados e modelos" });
    expect(entrada).toHaveTextContent("63%");
    expect(entrada).toHaveAccessibleDescription("Competição de modelos em andamento: 63%");
  });

  it("unlocks the journey when the stage is pronto", async () => {
    renderApp("/app/entrada");
    const entrada = await screen.findByRole("link", { name: "Entrada · dados e modelos" });
    await waitFor(() => expect(entrada).toHaveAccessibleDescription("Etapa concluída"));
    expect(entrada).toHaveAttribute("aria-current", "page");
    const report = screen.getByRole("link", { name: "Relatório executivo" });
    expect(report).not.toHaveAttribute("data-locked");
    expect(report).not.toHaveAttribute("aria-describedby");
  });

  it("flags the first step when there is no base yet", async () => {
    renderApp("/app/entrada", journeyFixture("dados"));
    const entrada = await screen.findByRole("link", { name: "Entrada · dados e modelos" });
    await waitFor(() => expect(entrada).toHaveAccessibleDescription("Carregue uma base para começar"));
  });

  it("shows the critical + high alerts badge", async () => {
    renderApp("/app/entrada", journeyFixture("pronto"), { critical: 1, high: 2 });
    expect(await screen.findByRole("link", { name: "Alertas 3 críticos ou altos" })).toHaveAttribute(
      "href",
      "/app/alerts",
    );
    expect(screen.getByRole("link", { name: "Alertas: 3 críticos ou altos" })).toBeInTheDocument(); // topbar bell
  });

  it("agrees the alerts count in the singular", async () => {
    renderApp("/app/entrada", journeyFixture("pronto"), { high: 1 });
    expect(await screen.findByRole("link", { name: "Alertas 1 crítico ou alto" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Alertas: 1 crítico ou alto" })).toBeInTheDocument();
  });

  it("the topbar has no dataset/run chip and does not request /api/data/active", async () => {
    const { api } = renderApp("/app/entrada");
    expect(await screen.findByRole("heading", { name: "Página Entrada" })).toBeInTheDocument();
    await waitFor(() => expect(api.count("/api/journey")).toBeGreaterThan(0));
    expect(api.count("/api/data/active")).toBe(0);
    expect(screen.queryByText(/dataset_2026_10_v01/)).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Pergunte ao analista de IA" })).toBeInTheDocument();
    expect(screen.getByText("Desenvolvido por")).toBeInTheDocument(); // signature card stays
  });
});

/* -------------------------------------------------------------------------- presentation */

describe("presentation mode (spec §1.6)", () => {
  it("?apresentacao=1 on the report hides sidebar, topbar and footer; the button leaves it", async () => {
    const { location } = renderApp("/app/relatorio/resumo?region=Sul&apresentacao=1");
    expect(await screen.findByRole("heading", { name: "Relatório resumo" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Navegação principal" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Pergunte ao analista de IA" })).not.toBeInTheDocument();
    expect(screen.queryByText("Desenvolvido por")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Sair da apresentação" }));
    await waitFor(() => expect(path(location())).toBe("/app/relatorio/resumo?region=Sul"));
    expect(screen.getByRole("navigation", { name: "Navegação principal" })).toBeInTheDocument();
    expect(h.mounts.relatorio).toBe(1);
  });

  it("Esc leaves presentation mode", async () => {
    const { location } = renderApp("/app/relatorio/meta?apresentacao=1");
    expect(await screen.findByRole("heading", { name: "Relatório meta" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(location().search).toBe(""));
    expect(screen.getByRole("navigation", { name: "Navegação principal" })).toBeInTheDocument();
  });

  it("is ignored outside the report", async () => {
    renderApp("/app/desvios?apresentacao=1");
    expect(await screen.findByRole("heading", { name: "Página Desvios" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Navegação principal" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sair da apresentação" })).not.toBeInTheDocument();
  });
});

/* --------------------------------------------------------------------------- journey state */

describe("JourneyGate (spec §1.5)", () => {
  it("shows progress for a running fixture", () => {
    mockApi({});
    renderWithProviders(<JourneyGate journey={journeyFixture("running")} />);
    expect(screen.getByText("Antes do relatório, a confiança")).toBeInTheDocument();
    expect(screen.getByText("Testando Litoral Market · SKU-10101")).toBeInTheDocument();
    expect(screen.getByText("136 de 220 séries · 63%")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "63");
    expect(screen.getByRole("link", { name: /Ir para a Entrada/ })).toHaveAttribute("href", "/app/entrada");
  });

  it('shows only "{step} · {pct}%" while done/total are null', () => {
    mockApi({});
    renderWithProviders(<JourneyGate journey={journeyFixture("queued")} />);
    expect(screen.getByText("Na fila · 0%")).toBeInTheDocument();
    expect(screen.queryByText(/séries/)).not.toBeInTheDocument();
  });

  it.each([
    ["dados", /Carregue uma base \(ou a demonstração\) e deixe os modelos competirem/],
    ["failed", /^A execução falhou: memória insuficiente/],
    ["none", /A base está pronta; falta rodar a competição de modelos\./],
  ] as const)("explains the %s state", (state, text) => {
    mockApi({});
    renderWithProviders(<JourneyGate journey={journeyFixture(state)} />);
    expect(screen.getByText(text)).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("reads the journey itself when no prop is given", async () => {
    mockApi({ "/api/journey": journeyFixture("dados") });
    renderWithProviders(<JourneyGate />);
    expect(await screen.findByText(/Carregue uma base/)).toBeInTheDocument();
  });

  it("runProgressLine formats pt-BR counts", () => {
    expect(runProgressLine({ progress: 0.634, step: "x", done: 1234, total: 2000 })).toBe(
      "1.234 de 2.000 séries · 63%",
    );
    expect(runProgressLine({ progress: null, step: null, done: null, total: null })).toBe(
      "Preparando a execução · 0%",
    );
  });
});

describe("RerunBanner", () => {
  it("names the run the numbers come from while a new run is in progress", () => {
    mockApi({});
    renderWithProviders(<RerunBanner journey={journeyFixture("rerunning")} />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Nova execução em andamento (63%) — os números abaixo são da execução RUN-20261026-053746 e serão atualizados ao final.",
    );
  });

  it("renders nothing otherwise", () => {
    mockApi({});
    const { container } = renderWithProviders(<RerunBanner journey={journeyFixture("pronto")} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("useJourney", () => {
  it("invalidates the other queries when a run goes from running to completed", async () => {
    let calls = 0;
    const api = mockApi({
      "/api/journey": () => (calls++ === 0 ? journeyFixture("running") : journeyFixture("pronto")),
      "/api/outra": { ok: true },
    });
    function Probe() {
      const { data } = useJourney();
      useGet<{ ok: boolean }>("/api/outra");
      return <span>{data?.run.state ?? "carregando"}</span>;
    }
    const { queryClient } = renderWithProviders(<Probe />);
    expect(await screen.findByText("running")).toBeInTheDocument();
    await waitFor(() => expect(api.count("/api/outra")).toBe(1));
    await act(() => queryClient.refetchQueries({ queryKey: JOURNEY_KEY }));
    expect(await screen.findByText("completed")).toBeInTheDocument();
    await waitFor(() => expect(api.count("/api/outra")).toBe(2));
  });

  it("refreshes the app once per completion, however many components use the journey", async () => {
    let calls = 0;
    const api = mockApi({
      "/api/journey": () => (calls++ === 0 ? journeyFixture("running") : journeyFixture("pronto")),
      "/api/outra": { ok: true },
    });
    function Probe({ id }: { id: string }) {
      const { data } = useJourney();
      return <span>{`${id}:${data?.run.state ?? "carregando"}`}</span>;
    }
    function Many() {
      useGet<{ ok: boolean }>("/api/outra");
      return (
        <>
          <Probe id="nav" />
          <Probe id="pagina" />
          <JourneyGate />
          <RerunBanner />
        </>
      );
    }
    const { queryClient } = renderWithProviders(<Many />);
    expect(await screen.findByText("pagina:running")).toBeInTheDocument();
    await waitFor(() => expect(api.count("/api/outra")).toBe(1));
    await act(() => queryClient.refetchQueries({ queryKey: JOURNEY_KEY }));
    expect(await screen.findByText("pagina:completed")).toBeInTheDocument();
    await waitFor(() => expect(api.count("/api/outra")).toBe(2));
    await act(() => new Promise((r) => setTimeout(r, 50)));
    expect(api.count("/api/outra")).toBe(2);
  });
});

/* -------------------------------------------------------------------------- CTAs / export */

describe("calls to action", () => {
  it("Home starts the journey at the Entrada", async () => {
    mockApi({ "/api/overview": { has_run: false, n_series: 220 }, "/api/meta": { models: [] } });
    renderWithProviders(undefined, { route: "/" });
    const start = await screen.findAllByRole("link", { name: /Começar/ });
    expect(start.length).toBeGreaterThanOrEqual(1);
    for (const a of start) expect(a).toHaveAttribute("href", "/app/entrada");
    const upload = screen.getAllByRole("link", { name: /Carregar meus dados/ });
    for (const a of upload) expect(a).toHaveAttribute("href", "/app/entrada?acao=carregar");
    expect(document.querySelector('a[href^="/app/overview"], a[href^="/app/data"]')).toBeNull();
  });

  it("ExportMenu downloads the executive report with the scope", () => {
    mockApi({});
    renderWithProviders(<ExportMenu scope={{ region: "Sul" }} />);
    expect(screen.getByRole("link", { name: /Baixar relatório \(HTML\)/ })).toHaveAttribute(
      "href",
      "/api/export/executive-html?download=true&region=Sul",
    );
    expect(screen.getByRole("link", { name: /Excel/ })).toHaveAttribute(
      "href",
      "/api/export/excel?region=Sul",
    );
  });
});
