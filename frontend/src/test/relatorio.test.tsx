/**
 * Stage 2 · Relatório executivo (spec §2.2, §5 F4 acceptance). The page renders on its own route
 * (`/app/relatorio/:capitulo`) with `mockApi`; links that leave the report are checked through the
 * router location. jsdom has no canvas, so `EChart` is mocked (the HTML charts render for real).
 */
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Emphasis } from "../components/story/Takeaways";
import { useFilters } from "../hooks/useFilters";
import { DEFAULT_PERIOD, parseDeviationState } from "../lib/deviationsUrl";
import { money } from "../lib/format";
import { REPORT_SCOPE_STORAGE_KEY } from "../lib/routes";
import Relatorio from "../pages/Relatorio";
import type { JourneyStatus } from "../types/journey";
import type { Chapter, Story } from "../types/story";
import storyFixture from "./fixtures/story.json";
import { journeyFixture, mockApi } from "./mockApi";
import { renderWithProviders } from "./render";

vi.mock("../charts/EChart", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../charts/EChart")>();
  const { createElement } = await import("react");
  return {
    ...actual,
    EChart: (props: { ariaLabel?: string }) =>
      createElement("div", { role: "img", "aria-label": props.ariaLabel, "data-testid": "echart" }),
  };
});

/* ------------------------------------------------------------------ helpers */

const CHAPTERS = ["resumo", "realizado", "precisao", "projecao", "gap", "meta", "decisoes"] as const;

const freshStory = () => structuredClone(storyFixture) as unknown as Story;
const chapterOf = (s: Story, id: string) => s.chapters.find((c) => c.id === id) as Chapter;

const DIMENSIONS = {
  region: ["Nordeste", "Sul"],
  channel: ["Atacarejo", "Varejo Moderno"],
  customer: [],
  category: ["Bebidas", "Snacks"],
  brand: [],
  sku: [],
  customers: [],
  series: [],
  last_actual: "2026-09-01",
  horizon: [],
};

function renderReport(
  route: string,
  {
    story = freshStory(),
    journey = journeyFixture("pronto"),
  }: { story?: Story; journey?: JourneyStatus } = {},
) {
  const api = mockApi({ "/api/journey": journey, "/api/story": story, "/api/data/dimensions": DIMENSIONS });
  const view = renderWithProviders(<Relatorio />, { route, path: "/app/relatorio/:capitulo" });
  return { ...view, api };
}

/** Waits for the chapter's H1. */
const h1 = () => screen.findByRole("heading", { level: 1 });
const path = (loc: { pathname: string; search: string }) => `${loc.pathname}${loc.search}`;
const visuals = () => document.querySelectorAll("[data-visual]");
const press = (key: string, init: KeyboardEventInit = {}) => fireEvent.keyDown(window, { key, ...init });

/** Rendered-text words that must never appear (spec §6.1.4). */
const ENGLISH = ["Budget", "Target", "Forecast error", "Loading", "Error", "Next", "Previous", "Revenue"];

/* -------------------------------------------------------------------- tests */

describe("Relatório executivo · shell", () => {
  it("Resumo: governing thought as H1, SCQA, 4 KPI cards without icons and 'O roteiro' with chapters 2–7", async () => {
    const s = freshStory();
    renderReport("/app/relatorio/resumo");
    expect(await h1()).toHaveTextContent(s.governing_thought);
    expect(screen.getByText("Etapa 2 de 3 · Relatório executivo · Ciclo S&OP out/2026")).toBeInTheDocument();
    expect(screen.getByText("Capítulo 1 de 7")).toBeInTheDocument();

    const scqa = screen.getByLabelText("Situação, complicação e resposta");
    expect(within(scqa).getByText("Situação").tagName).toBe("DT");
    expect(scqa).toHaveTextContent(s.scqa.resposta);

    expect(visuals()).toHaveLength(1);
    const kpis = document.querySelector('[data-visual="kpis"]') as HTMLElement;
    expect(kpis).toHaveAttribute("data-question", chapterOf(s, "resumo").question);
    const cards = kpis.querySelectorAll(".card");
    expect(cards).toHaveLength(4);
    kpis
      .querySelectorAll(".card")
      .forEach((c) => expect(c.querySelector("[aria-hidden].bg-gradient-to-br")).toBeNull());
    expect(kpis).toHaveTextContent(money(87860615.79));

    const roteiro = document.querySelectorAll("[data-roteiro]");
    expect([...roteiro].map((a) => a.getAttribute("data-roteiro"))).toEqual(CHAPTERS.slice(1));
    expect(roteiro[0]).toHaveTextContent(chapterOf(s, "realizado").headline);
    expect(roteiro[0]).toHaveAttribute("href", "/app/relatorio/realizado");
  });

  it("rail: 7 chips with aria-current on the current one, progress text and the disclosure line", async () => {
    renderReport("/app/relatorio/gap?region=Sul");
    await h1();
    const nav = screen.getByRole("navigation", { name: "Capítulos" });
    const chips = within(nav).getAllByRole("link");
    expect(chips).toHaveLength(7);
    expect(within(nav).getByRole("link", { current: "step" })).toHaveTextContent("Gap vs orçamento");
    expect(chips[3]).toHaveTextContent("Próximos 12 meses");
    expect(chips[0]).toHaveAttribute("href", "/app/relatorio/resumo?region=Sul");
    expect(screen.getByText("Capítulo 5 de 7")).toBeInTheDocument();
    // The frame's eyebrow names the chapter by its title (the rail chips use the short name).
    expect(screen.getByText("Capítulo 5 de 7 · Gap vs orçamento")).toBeInTheDocument();
    expect(document.querySelector("[data-disclosure]")).toHaveTextContent(
      "Base dataset_2026_10_v01 · execução RUN-20261026-053746 · orçamento: Orçamento anual e metas de vendas sintéticos · erro de previsão medido em backtest fora da amostra (1–3 meses de antecedência).",
    );
  });

  it("←/→ moves /app/relatorio/precisao to projecao and back; Home/End/PageUp/PageDown; no new /api/story request", async () => {
    const { location, api } = renderReport("/app/relatorio/precisao");
    await h1();
    press("ArrowRight");
    await waitFor(() => expect(location().pathname).toBe("/app/relatorio/projecao"));
    expect(screen.getByText("Capítulo 4 de 7")).toBeInTheDocument();
    expect(await h1()).toHaveTextContent(chapterOf(freshStory(), "projecao").headline);

    press("ArrowLeft");
    await waitFor(() => expect(location().pathname).toBe("/app/relatorio/precisao"));
    press("PageDown");
    await waitFor(() => expect(location().pathname).toBe("/app/relatorio/projecao"));
    press("PageUp");
    await waitFor(() => expect(location().pathname).toBe("/app/relatorio/precisao"));
    press("End");
    await waitFor(() => expect(location().pathname).toBe("/app/relatorio/decisoes"));
    press("ArrowRight"); // already on the last chapter
    press("Home");
    await waitFor(() => expect(location().pathname).toBe("/app/relatorio/resumo"));
    press("ArrowLeft"); // already on the first chapter
    expect(location().pathname).toBe("/app/relatorio/resumo");

    expect(api.count("/api/story")).toBe(1);
  });

  it("ignores the keys inside a select and with Ctrl (print, browser shortcuts)", async () => {
    const { location } = renderReport("/app/relatorio/realizado");
    await h1();
    fireEvent.keyDown(screen.getByRole("combobox", { name: "Escopo do relatório" }), { key: "ArrowRight" });
    press("p", { ctrlKey: true });
    press("ArrowRight", { ctrlKey: true });
    expect(path(location())).toBe("/app/relatorio/realizado");
  });

  it("every chapter renders exactly one [data-visual] with a question, ≤ 3 takeaways and pt-BR text only", async () => {
    const s = freshStory();
    const { api } = renderReport("/app/relatorio/resumo");
    await h1();
    for (const id of CHAPTERS) {
      fireEvent.click(
        within(screen.getByRole("navigation", { name: "Capítulos" })).getAllByRole("link")[
          CHAPTERS.indexOf(id)
        ],
      );
      await waitFor(() => expect(document.querySelector(`[data-chapter-frame="${id}"]`)).not.toBeNull());
      const ch = chapterOf(s, id);
      expect(visuals()).toHaveLength(1);
      expect(visuals()[0]).toHaveAttribute("data-visual", ch.visual.kind);
      expect(visuals()[0].getAttribute("data-question")).toBe(ch.question);
      expect(document.querySelectorAll("[data-takeaway]").length).toBeLessThanOrEqual(3);
      expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
        id === "resumo" ? s.governing_thought : ch.headline,
      );
      const text = document.body.textContent ?? "";
      for (const w of ENGLISH) expect(text).not.toMatch(new RegExp(`\\b${w}\\b`));
    }
    expect(api.count("/api/story")).toBe(1);
  });

  it("'Próximo' walks the story without new requests; the last chapter offers 'Investigar os desvios'", async () => {
    const { location, api } = renderReport("/app/relatorio/meta?channel=Atacarejo");
    await h1();
    fireEvent.click(screen.getByRole("link", { name: /Próximo: Decisões para hoje/ }));
    await waitFor(() => expect(path(location())).toBe("/app/relatorio/decisoes?channel=Atacarejo"));
    // The footer link left with the old chapter: focus lands on the new chapter's H1.
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("heading", { level: 1 })));
    expect(screen.queryByRole("link", { name: /^Próximo:/ })).toBeNull();
    // One door into stage 3: the deep dive's default view with the scope (not the chapter's series level).
    expect(chapterOf(freshStory(), "decisoes").investigate?.params.nivel).toBe("series");
    expect(screen.queryByRole("link", { name: /Investigar no deep dive/ })).toBeNull();
    const exit = screen.getByRole("link", { name: /Investigar os desvios/ });
    expect(exit).toHaveAttribute("href", "/app/desvios?channel=Atacarejo&de=decisoes");
    // "← Meta" goes back one chapter.
    const footer = screen.getByRole("navigation", { name: "Navegação do capítulo" });
    fireEvent.click(within(footer).getByRole("link", { name: "Meta" }));
    await waitFor(() => expect(path(location())).toBe("/app/relatorio/meta?channel=Atacarejo"));
    expect(api.count("/api/story")).toBe(1);
  });
});

describe("Relatório executivo · ações", () => {
  it("'Investigar no deep dive' opens /app/desvios with the chapter's cmp/periodo/nivel, the scope path and de", async () => {
    const { location } = renderReport("/app/relatorio/realizado?region=Sul&apresentacao=1");
    await h1();
    const link = screen.getByRole("link", { name: /Investigar no deep dive/ });
    // Links out of the report never carry `apresentacao` (spec §1.6).
    expect(link).toHaveAttribute("href", "/app/desvios?cmp=ac_pl&region=Sul&nivel=customer&de=realizado");
    fireEvent.click(link);
    await waitFor(() => expect(location().pathname).toBe("/app/desvios"));
    const s = parseDeviationState(new URLSearchParams(location().search));
    expect(s.cmp).toBe("ac_pl");
    expect(s.periodo ?? DEFAULT_PERIOD[s.cmp]).toBe("u12m");
    expect(s.nivel).toBe("customer");
    expect(s.path).toEqual({ region: "Sul" });
    expect(s.de).toBe("realizado");
  });

  it("drops a breakdown level already fixed by the scope (nivel=region with region=Sul)", async () => {
    renderReport("/app/relatorio/projecao?region=Sul");
    await h1();
    expect(screen.getByRole("link", { name: /Investigar no deep dive/ })).toHaveAttribute(
      "href",
      "/app/desvios?region=Sul&de=projecao",
    );
  });

  it("takeaway links and a click on a VarianceBars member open the deep dive focused on it", async () => {
    const { location } = renderReport("/app/relatorio/gap");
    await h1();
    const takeaway = screen.getAllByRole("link", { name: /Ver no deep dive/ })[0];
    expect(takeaway).toHaveAttribute("href", "/app/desvios?nivel=customer&sel=Litoral%20Market&de=gap");

    const bars = document.querySelector('[data-visual="variance_bars"]') as HTMLElement;
    fireEvent.click(within(bars).getByRole("button", { name: /Rede Horizonte Supermercados/ }));
    await waitFor(() => expect(location().pathname).toBe("/app/desvios"));
    const s = parseDeviationState(new URLSearchParams(location().search));
    expect(s).toMatchObject({
      cmp: "fc_pl",
      nivel: "customer",
      sel: "Rede Horizonte Supermercados",
      de: "gap",
    });
  });

  it("'Perguntar à IA' copies the report scope to the filters and opens the analyst with the chapter question", async () => {
    const { location: loc } = renderReport("/app/relatorio/meta?region=Nordeste");
    act(() => useFilters.setState({ filters: { customer: "Litoral Market" } }));
    await h1();
    fireEvent.click(screen.getByRole("button", { name: /Perguntar à IA/ }));
    await waitFor(() => expect(loc().pathname).toBe("/app/ai"));
    expect(new URLSearchParams(loc().search).get("q")).toBe("A meta é realista?");
    expect(useFilters.getState().filters).toEqual({ region: "Nordeste" });
  });

  it("hides 'Perguntar à IA' when ask_ai is null and shows the secondary action of Meta", async () => {
    const s = freshStory();
    chapterOf(s, "realizado").ask_ai = null;
    renderReport("/app/relatorio/realizado", { story: s });
    await h1();
    expect(screen.queryByRole("button", { name: /Perguntar à IA/ })).toBeNull();
    fireEvent.click(screen.getByRole("link", { name: /Próximo: Precisão/ }));
    expect(await screen.findByRole("button", { name: /Perguntar à IA/ })).toBeInTheDocument();
    press("End");
    press("ArrowLeft");
    expect(await screen.findByRole("link", { name: "Simular alavanca" })).toHaveAttribute(
      "href",
      "/app/scenarios?distribution_change_pct=0.133",
    );
  });

  it("P toggles ?apresentacao=1 and the presentation hides the header controls", async () => {
    const { location } = renderReport("/app/relatorio/gap?region=Sul");
    await h1();
    expect(screen.getByRole("combobox", { name: "Escopo do relatório" })).toBeInTheDocument();
    press("P");
    await waitFor(() => expect(path(location())).toBe("/app/relatorio/gap?region=Sul&apresentacao=1"));
    expect(screen.queryByRole("combobox", { name: "Escopo do relatório" })).toBeNull();
    // Chapter links keep the presentation; the scope chip stays visible for the audience.
    expect(screen.getByRole("link", { name: /Próximo: Viabilidade da meta/ })).toHaveAttribute(
      "href",
      "/app/relatorio/meta?region=Sul&apresentacao=1",
    );
    expect(document.querySelector("[data-scope-chip]")).toHaveTextContent("Escopo: Sul");
    press("p");
    await waitFor(() => expect(path(location())).toBe("/app/relatorio/gap?region=Sul"));
  });

  it("'Apresentar' button enters presentation mode", async () => {
    const { location } = renderReport("/app/relatorio/resumo");
    await h1();
    fireEvent.click(screen.getByRole("button", { name: /Apresentar/ }));
    await waitFor(() => expect(location().search).toBe("?apresentacao=1"));
  });
});

describe("Relatório executivo · escopo", () => {
  it("the Escopo select writes the URL, mirrors useFilters, saves the session and refetches the story", async () => {
    sessionStorage.clear();
    const { location, api } = renderReport("/app/relatorio/gap");
    await h1();
    const select = screen.getByRole("combobox", { name: "Escopo do relatório" });
    await waitFor(() => expect(within(select).getByRole("option", { name: "Sul" })).toBeInTheDocument());
    expect(
      within(select)
        .getAllByRole("group")
        .map((g) => g.getAttribute("label")),
    ).toEqual(["Região", "Canal", "Categoria"]);
    fireEvent.change(select, { target: { value: "region=Sul" } });
    await waitFor(() => expect(path(location())).toBe("/app/relatorio/gap?region=Sul"));
    expect(useFilters.getState().filters).toEqual({ region: "Sul" });
    expect(JSON.parse(sessionStorage.getItem(REPORT_SCOPE_STORAGE_KEY) ?? "{}")).toEqual({ region: "Sul" });
    await waitFor(() => expect(api.count("/api/story")).toBe(2));
    expect(api.requests("/api/story")[1].params.get("region")).toBe("Sul");
    expect(document.querySelector("[data-scope-chip]")).toHaveTextContent("Escopo: Sul");

    fireEvent.click(screen.getByRole("button", { name: "Remover escopo Sul" }));
    await waitFor(() => expect(path(location())).toBe("/app/relatorio/gap"));
    expect(useFilters.getState().filters).toEqual({});
    expect(sessionStorage.getItem(REPORT_SCOPE_STORAGE_KEY)).toBeNull();
    expect(document.querySelector("[data-scope-chip]")).toHaveTextContent("Escopo: Empresa toda");
  });

  it("a scope that arrives in the URL is kept for the session and shown in the select before the dimensions load", async () => {
    sessionStorage.clear();
    renderReport("/app/relatorio/resumo?category=Higiene");
    await h1();
    expect(screen.getByRole("combobox", { name: "Escopo do relatório" })).toHaveValue("category=Higiene");
    expect(JSON.parse(sessionStorage.getItem(REPORT_SCOPE_STORAGE_KEY) ?? "{}")).toEqual({
      category: "Higiene",
    });
  });
});

describe("Relatório executivo · estados", () => {
  it("an empty chapter shows its notice with H1 = title and hides 'Investigar no deep dive'", async () => {
    const s = freshStory();
    const notice = "Sem orçamento/meta nesta base — envie a aba 'Plano (opcional)' do modelo de planilha.";
    // The shape B3 sends for an empty chapter: headline = title, no data, no actions.
    Object.assign(chapterOf(s, "gap"), {
      status: "empty",
      notice,
      headline: "Gap vs orçamento",
      visual: { kind: "variance_bars", data: null },
      investigate: null,
      secondary_action: null,
      ask_ai: null,
      takeaways: [],
    });
    renderReport("/app/relatorio/gap", { story: s });
    expect(await h1()).toHaveTextContent("Gap vs orçamento");
    expect(document.querySelector("[data-chapter-notice]")).toHaveTextContent(notice);
    expect(screen.queryByRole("link", { name: /Investigar no deep dive/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Perguntar à IA/ })).toBeNull();
    expect(visuals()).toHaveLength(0);
    const chip = document.querySelector('[data-chapter="gap"]');
    expect(chip).toHaveAttribute("data-empty", "true");
    expect(chip).toHaveAttribute("href", "/app/relatorio/gap");
  });

  it("**…** renders as <strong> and an unmatched marker stays plain", async () => {
    renderReport("/app/relatorio/realizado");
    await h1();
    const strong = screen.getByText("+15,2%");
    expect(strong.tagName).toBe("STRONG");
    expect(document.body.textContent).not.toContain("**");

    const { container } = render(<Emphasis text="a **b** c **d" />);
    expect(container.querySelectorAll("strong")).toHaveLength(1);
    expect(container.textContent).toBe("a b c d");
  });

  it("no story component injects HTML (no dangerouslySetInnerHTML)", () => {
    const sources = import.meta.glob(["../components/story/*.{ts,tsx}", "../pages/Relatorio.tsx"], {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>;
    expect(Object.keys(sources).length).toBeGreaterThanOrEqual(8);
    for (const [file, src] of Object.entries(sources)) {
      expect(src, file).not.toContain("dangerouslySetInnerHTML");
      expect(src, file).not.toMatch(/\btruncate\b|line-clamp|border-l-/);
    }
  });

  it("Decisões: full-width table, impacts with their basis, deep-dive links tagged with de=decisoes", async () => {
    const s = freshStory();
    renderReport("/app/relatorio/decisoes");
    await h1();
    const rows = document.querySelectorAll("[data-decision]");
    expect(rows).toHaveLength(5);
    expect(rows[0]).toHaveAttribute("data-decision", "D4");
    expect(rows[0]).toHaveTextContent(money(11702453.39));
    expect(rows[0]).toHaveTextContent("nos próximos 12 meses");
    expect(within(rows[0] as HTMLElement).getByRole("link")).toHaveAttribute(
      "href",
      "/app/scenarios?distribution_change_pct=0.133",
    );
    const d2 = document.querySelector('[data-decision="D2"]') as HTMLElement;
    expect(d2).toHaveTextContent("erro anualizado da janela de backtest");
    expect(within(d2).getByRole("link")).toHaveAttribute(
      "href",
      "/app/desvios?lente=previsao&cmp=ac_fc&nivel=customer&causa=promocao&de=decisoes",
    );
    expect(screen.getByText(/nenhum número é gerado por IA/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Perguntar à IA/ })).toBeNull();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(chapterOf(s, "decisoes").headline);
  });

  it("derived plan: persistent amber chip under the header", async () => {
    const s = freshStory();
    s.reference.plan_derived = true;
    renderReport("/app/relatorio/resumo", { story: s });
    await h1();
    expect(document.querySelector("[data-plan-derived]")).toHaveTextContent(
      "Orçamento estimado automaticamente — desvios vs orçamento são ilustrativos.",
    );
  });

  it("story.available === false shows an EmptyState with the reason", async () => {
    renderReport("/app/relatorio/resumo", {
      story: { available: false, reason: "Ainda não há uma execução de forecast concluída." } as Story,
    });
    expect(await screen.findByText("Relatório indisponível")).toBeInTheDocument();
    expect(screen.getByText("Ainda não há uma execução de forecast concluída.")).toBeInTheDocument();
    expect(visuals()).toHaveLength(0);
  });

  it("stage !== pronto renders the JourneyGate and never asks for the story", async () => {
    const { api } = renderReport("/app/relatorio/resumo", { journey: journeyFixture("running") });
    expect(await screen.findByText("Antes do relatório, a confiança")).toBeInTheDocument();
    expect(api.count("/api/story")).toBe(0);
  });

  it("an unknown chapter in the URL falls back to the first chapter of the story", async () => {
    renderReport("/app/relatorio/xyz");
    expect(await h1()).toHaveTextContent(freshStory().governing_thought);
  });
});
