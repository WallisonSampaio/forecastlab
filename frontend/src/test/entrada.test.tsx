/**
 * F3 · Stage 1, Entrada (spec §2.1, §5 F3 acceptance). Network is stubbed by pathname with `mockApi`;
 * the ECharts canvas is replaced by a plain element that records its props (jsdom has no canvas).
 */
import { configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { lagSentence } from "../components/entrada/helpers";
import { ModelScoreboard, REFERENCE_TOOLTIP } from "../components/entrada/ModelScoreboard";
import { deviationsHref } from "../lib/deviationsUrl";
import { full, money, pct, pp } from "../lib/format";
import Entrada from "../pages/Entrada";
import type { DatasetInfo, Issue } from "../types";
import type { JourneyStatus } from "../types/journey";
import type { Trust } from "../types/trust";
import trustFixtures from "./fixtures/trust.json";
import { journeyFixture, mockApi, reply, type MockHandler } from "./mockApi";
import { renderWithProviders } from "./render";

configure({ asyncUtilTimeout: 5000 });

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const echart = vi.hoisted(() => ({ calls: [] as { option: any; ariaLabel?: string }[] }));

vi.mock("../charts/EChart", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../charts/EChart")>();
  const { createElement } = await import("react");
  return {
    ...actual,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    EChart: (props: { option: any; ariaLabel?: string }) => {
      echart.calls.push(props);
      return createElement("div", { role: "img", "aria-label": props.ariaLabel, "data-testid": "echart" });
    },
  };
});

/* ------------------------------------------------------------------ fixtures */

const trustFixture = (): Trust => structuredClone(trustFixtures.confiavel) as Trust;

const warningIssue: Issue = {
  severity: "warning",
  code: "outliers",
  message: "8 outliers sem explicação",
  count: 8,
  examples: [],
};
const criticalIssue: Issue = {
  severity: "critical",
  code: "missing_columns",
  message: "Colunas obrigatórias ausentes: units",
  count: 1,
  examples: ["units"],
};

const validation = (issues: Issue[], status: "valid" | "warnings" | "blocked") => ({
  status,
  can_forecast: status !== "blocked",
  blocking_message: null,
  summary: {},
  quality: { completeness: 100, consistency: 100, historical_depth: 100, granularity: 100, overall: 100 },
  issues,
  column_mapping: {},
  missing_optional: [],
});

const activeDataset: DatasetInfo = {
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
  status: "warnings",
  is_active: true,
  plan_source: "Orçamento anual e metas de vendas sintéticos",
  validation: validation([warningIssue], "warnings"),
};

/** Every request the page makes (plus the forecast job polled by `RunForecastButton`). */
function routes(journey: JourneyStatus, extra: Record<string, MockHandler> = {}) {
  return {
    "/api/journey": journey,
    "/api/data/active": activeDataset,
    "/api/models/trust": trustFixture(),
    "/api/forecast/job": null,
    ...extra,
  };
}

const renderEntrada = (route = "/app/entrada") => renderWithProviders(<Entrada />, { route });
const title = () => screen.findByRole("heading", { level: 1, name: "Dados e modelos" });
const stepNode = (label: string) =>
  within(screen.getByRole("list", { name: "Etapas da entrada" }))
    .getByText(label)
    .closest("li") as HTMLElement;
const card = (visual: string) => document.querySelector(`[data-visual="${visual}"]`) as HTMLElement;

function pickFile(name = "vendas.xlsx") {
  const input = screen.getByTestId("arquivo-base") as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["x"], name)] } });
}

/* --------------------------------------------------------------------- tests */

describe("Entrada · etapa dados", () => {
  it("shows the two option cards and a template link to /api/data/template", async () => {
    mockApi(routes(journeyFixture("dados")));
    renderEntrada();
    await title();
    expect(await screen.findByText("Usar base de demonstração")).toBeInTheDocument();
    expect(screen.getByText("Enviar minha planilha")).toBeInTheDocument();
    const template = screen.getByRole("link", { name: /Baixar modelo de planilha \(\.xlsx\)/ });
    expect(template.getAttribute("href")).toMatch(/\/api\/data\/template$/);
    expect(screen.getByText(/Arraste o arquivo ou clique para escolher/)).toBeInTheDocument();
    expect(
      screen.getByText(/Colunas mínimas: Data, Região, Canal, Cliente, SKU e Unidades/),
    ).toBeInTheDocument();

    // stepper: step 1 is the current one, steps 2 and 3 wait
    expect(stepNode("Base de dados")).toHaveAttribute("aria-current", "step");
    expect(stepNode("Competição de modelos")).toHaveTextContent("Aguardando a base");
    expect(stepNode("Confiança no forecast")).toHaveTextContent("Aguardando a competição");
  });

  it("loads the demo with seed 42 and announces that the competition started", async () => {
    const api = mockApi(
      routes(journeyFixture("dados"), {
        "POST /api/data/demo": { dataset_version: "dataset_2026_10_v02", run_id: "RUN-1" },
      }),
    );
    renderEntrada();
    fireEvent.click(await screen.findByRole("button", { name: /Carregar demonstração e rodar forecast/ }));
    expect(await screen.findByText("Base válida — a competição de modelos já começou.")).toBeInTheDocument();
    expect(api.requests("/api/data/demo")[0].body).toEqual({ seed: 42, run_forecast: true });
  });

  it("the 'já começou' card stays while the run is going and leaves once it completed", async () => {
    let journey = journeyFixture("dados");
    mockApi(
      routes(journeyFixture("dados"), {
        "/api/journey": () => journey,
        "POST /api/data/demo": () => {
          journey = journeyFixture("running");
          return { dataset_version: "dataset_2026_10_v01", run_id: "RUN-20261026-053746" };
        },
      }),
    );
    const { queryClient } = renderEntrada();
    fireEvent.click(await screen.findByRole("button", { name: /Carregar demonstração e rodar forecast/ }));
    await waitFor(() => expect(card("competicao")).toHaveTextContent("136 de 220 séries"));
    expect(screen.getByText("Base válida — a competição de modelos já começou.")).toBeInTheDocument();
    journey = journeyFixture("pronto");
    await queryClient.invalidateQueries();
    await screen.findByTestId("veredito");
    expect(screen.queryByText("Base válida — a competição de modelos já começou.")).not.toBeInTheDocument();
  });

  it("a blocked upload lists the critical issues and step 2 stays waiting", async () => {
    mockApi(
      routes(journeyFixture("dados"), {
        "POST /api/data/upload": {
          file_name: "vendas.xlsx",
          accepted: false,
          dataset_version: null,
          run_id: null,
          validation: validation([criticalIssue, warningIssue], "blocked"),
          quality_label: "Baixa",
        },
      }),
    );
    renderEntrada();
    await screen.findByText("Enviar minha planilha");
    pickFile();
    const blocked = await screen.findByTestId("upload-bloqueado");
    expect(blocked).toHaveTextContent("A base tem erros críticos e não foi carregada.");
    expect(blocked).toHaveTextContent("Coluna obrigatória ausente: Unidades");
    // only the critical issue is listed
    expect(within(blocked).getAllByRole("listitem")).toHaveLength(1);
    expect(within(blocked).getByRole("link", { name: /Baixar modelo de planilha/ })).toHaveAttribute(
      "href",
      expect.stringMatching(/\/api\/data\/template$/),
    );
    expect(stepNode("Base de dados")).toHaveTextContent("Base recusada na validação");
    expect(stepNode("Competição de modelos")).toHaveTextContent("Aguardando a base");
    expect(document.body.textContent).not.toContain("já começou");
  });

  it("'Manter a base atual' dismisses a blocked attempt and the stepper error", async () => {
    mockApi(
      routes(journeyFixture("pronto"), {
        "POST /api/data/upload": {
          file_name: "vendas.xlsx",
          accepted: false,
          dataset_version: null,
          run_id: null,
          validation: validation([criticalIssue], "blocked"),
          quality_label: "Baixa",
        },
      }),
    );
    renderEntrada("/app/entrada?acao=carregar");
    await screen.findByText("Enviar minha planilha");
    pickFile();
    expect(await screen.findByTestId("upload-bloqueado")).toHaveTextContent(
      "A base tem erros críticos e não foi carregada. A base anterior continua ativa.",
    );
    expect(stepNode("Base de dados")).toHaveTextContent("Base recusada na validação");
    fireEvent.click(screen.getByRole("button", { name: "Manter a base atual" }));
    expect(screen.queryByTestId("upload-bloqueado")).not.toBeInTheDocument();
    expect(stepNode("Base de dados")).toHaveTextContent("Base validada");
  });

  it("an accepted upload whose run did not start shows the amber card with RunForecastButton", async () => {
    mockApi(
      routes(journeyFixture("dados"), {
        "POST /api/data/upload": {
          file_name: "vendas.xlsx",
          accepted: true,
          dataset_version: "dataset_2026_10_v02",
          run_id: null,
          run_message: "Já existe uma execução de forecast em andamento.",
          validation: validation([], "valid"),
          quality_label: "Excelente",
        },
      }),
    );
    renderEntrada();
    await screen.findByText("Enviar minha planilha");
    pickFile();
    const card = await screen.findByTestId("upload-sem-execucao");
    expect(card).toHaveTextContent(
      "Base carregada e ativada, mas a competição de modelos não começou: Já existe uma execução de forecast em andamento.",
    );
    expect(within(card).getByRole("button", { name: /Rodar forecast/ })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("já começou");
  });

  it("an accepted upload with warnings says how many were treated", async () => {
    mockApi(
      routes(journeyFixture("dados"), {
        "POST /api/data/upload": {
          file_name: "vendas.xlsx",
          accepted: true,
          dataset_version: "dataset_2026_10_v02",
          run_id: "RUN-2",
          validation: validation([warningIssue], "warnings"),
          quality_label: "Excelente",
        },
      }),
    );
    renderEntrada();
    await screen.findByText("Enviar minha planilha");
    pickFile();
    expect(
      await screen.findByText(
        "Base aceita com 1 aviso tratado automaticamente — a competição de modelos já começou.",
      ),
    ).toBeInTheDocument();
  });

  it("a rejected upload (HTTP 400) shows the backend's pt-BR detail", async () => {
    mockApi(
      routes(journeyFixture("dados"), {
        "POST /api/data/upload": reply(400, { detail: "Tipo de arquivo não suportado (.txt)." }),
      }),
    );
    renderEntrada();
    await screen.findByText("Enviar minha planilha");
    pickFile("vendas.txt");
    expect(await screen.findByText("Tipo de arquivo não suportado (.txt).")).toBeInTheDocument();
    expect(stepNode("Base de dados")).toHaveTextContent("Base recusada na validação");
  });
});

describe("Entrada · etapa modelos", () => {
  it("a running fixture shows the progress, {done} de {total} séries and the percentage", async () => {
    mockApi(routes(journeyFixture("running")));
    renderEntrada();
    const models = await waitFor(() => {
      const c = card("competicao");
      expect(c).toHaveTextContent("136 de 220 séries");
      return c;
    });
    expect(models).toHaveTextContent("63%");
    expect(models).toHaveTextContent("Testando Litoral Market · SKU-10101");
    expect(within(models).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "63");
    expect(stepNode("Competição de modelos")).toHaveAttribute("aria-current", "step");
    // step 1 collapsed to its summary line
    expect(card("base")).toHaveTextContent("Base validada: 220 séries Cliente × SKU");
    expect(screen.queryByText("Usar base de demonstração")).not.toBeInTheDocument();
  });

  it("while a run is in progress the dropzone and the demo button are disabled", async () => {
    mockApi(routes(journeyFixture("running")));
    renderEntrada("/app/entrada?acao=carregar");
    const demo = await screen.findByRole("button", { name: /Carregar demonstração e rodar forecast/ });
    expect(demo).toBeDisabled();
    expect(screen.getByTestId("dropzone")).toBeDisabled();
    expect(screen.getByTestId("arquivo-base")).toBeDisabled();
    expect(screen.getByText("Aguarde a execução atual terminar.")).toBeInTheDocument();
  });

  it("a run that was never started offers RunForecastButton with the RunParams defaults", async () => {
    mockApi(routes(journeyFixture("none")));
    renderEntrada();
    const models = await waitFor(() => {
      const c = card("competicao");
      expect(c).toHaveTextContent("de 15 disponíveis");
      return c;
    });
    expect(models).toHaveTextContent("em 4 janelas fora da amostra de 3 meses");
    expect(within(models).getByRole("button", { name: /Rodar forecast/ })).toBeInTheDocument();
  });

  it("a failed run shows the message and 'Tentar novamente'", async () => {
    mockApi(routes(journeyFixture("failed")));
    renderEntrada();
    // the backend message already reads "A execução falhou: …" and is shown as is (no doubled prefix)
    expect(
      await screen.findByText("A execução falhou: memória insuficiente para o backtest."),
    ).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/falhou: A execução falhou/);
    expect(screen.getByRole("button", { name: /Tentar novamente/ })).toBeInTheDocument();
    expect(stepNode("Competição de modelos")).toHaveTextContent("A execução falhou");
  });
});

describe("Entrada · etapa pronto", () => {
  it("shows the verdict, 4 KPI cards, the backtest line, ≤ 5 caution rows and opens the report", async () => {
    echart.calls.length = 0;
    const api = mockApi(routes(journeyFixture("pronto")));
    const tr = trustFixture();
    renderEntrada();
    const verdict = await screen.findByTestId("veredito");
    expect(verdict).toHaveAttribute("data-verdict", "confiavel");
    expect(verdict).toHaveTextContent("Confiável para decisão");
    expect(verdict).toHaveTextContent(tr.verdict.headline);

    const kpis = screen.getByTestId("kpis-confianca");
    expect(kpis.children).toHaveLength(4);
    expect(kpis).toHaveTextContent(`Acurácia fora da amostra${pct(tr.accuracy, 1)}`);
    expect(kpis).toHaveTextContent(`WMAPE ${pct(tr.wmape, 1)} · em unidades`);
    expect(kpis).toHaveTextContent(pct(tr.bias, 1, true));
    expect(kpis).toHaveTextContent("Equilibrado");
    expect(kpis).toHaveTextContent(pp(tr.gain_vs_naive_pp));
    expect(kpis).toHaveTextContent(`ingênuo ${pct(tr.naive_wmape, 1)} → estatístico ${pct(tr.wmape, 1)}`);
    expect(kpis).toHaveTextContent(pct(tr.confidence_revenue_share.High, 0));
    expect(kpis).toHaveTextContent(`${full(135)} de ${full(220)} séries`);
    // journey KPI cards carry no icon tile
    expect(kpis.querySelector("[aria-hidden].bg-gradient-to-br")).toBeNull();

    expect(screen.getByRole("img", { name: "Real vs previsto fora da amostra (R$)" })).toBeInTheDocument();
    expect(echart.calls.at(-1)?.option.series[0].data).toHaveLength(12);
    expect(screen.getByTestId("erro-por-antecedencia")).toHaveTextContent(
      "O erro vai de 13,3% (1 mês de antecedência) a 14,8% (3 meses).",
    );

    const caution = screen.getByTestId("cautela").querySelectorAll("li");
    expect(caution.length).toBeGreaterThan(0);
    expect(caution.length).toBeLessThanOrEqual(5);
    const first = tr.caution[0];
    expect(caution[0]).toHaveTextContent(`${first.customer} · ${first.sku} ${first.product}`);
    expect(caution[0]).toHaveTextContent(`Receita 12M ${money(first.revenue_12m)}`);
    expect(within(caution[0] as HTMLElement).getByRole("link", { name: /Investigar/ })).toHaveAttribute(
      "href",
      deviationsHref({
        cmp: "ac_fc",
        path: { customer: first.customer, sku: first.sku },
        nivel: "series",
        serie: first.series_id,
      }),
    );

    expect(screen.getByTestId("abrir-relatorio")).toHaveAttribute("href", "/app/relatorio/resumo");
    expect(screen.getByTestId("abrir-relatorio")).toHaveTextContent("Abrir o relatório");
    expect(screen.getByRole("link", { name: "Ver governança dos modelos" })).toHaveAttribute(
      "href",
      "/app/models",
    );
    // header actions: rerun + open the report
    expect(screen.getByRole("button", { name: /Rodar novamente/ })).toBeInTheDocument();

    // step 1 collapsed to its summary, step 2 shows the competition result, step 3 current
    expect(stepNode("Confiança no forecast")).toHaveAttribute("aria-current", "step");
    expect(screen.queryByText("Usar base de demonstração")).not.toBeInTheDocument();
    const boardRows = screen.getByTestId("placar").querySelectorAll("li");
    expect(boardRows.length).toBeGreaterThan(0);
    expect(boardRows.length).toBeLessThanOrEqual(7);
    expect(card("base")).toHaveTextContent("Orçamento e meta: base de demonstração");
    expect(card("competicao")).toHaveTextContent(
      `15 modelos competiram em 220 séries; o campeão de cada série erra ${pct(tr.wmape, 1)}, ${pp(
        tr.gain_vs_naive_pp,
      )} a menos que o método ingênuo.`,
    );

    // request budget: journey + active + trust (+ the job polled by the shell's RunStatus)
    expect(api.count("/api/models/trust")).toBe(1);
    expect(api.count("/api/data/active")).toBe(1);
  });

  it("at most 5 visual blocks, each with a question", async () => {
    mockApi(routes(journeyFixture("pronto")));
    renderEntrada();
    await screen.findByTestId("veredito");
    const blocks = document.querySelectorAll("[data-visual]");
    expect(blocks.length).toBeGreaterThan(0);
    expect(blocks.length).toBeLessThanOrEqual(5);
    blocks.forEach((b) => expect(b.getAttribute("data-question")?.trim()).toBeTruthy());
  });

  it("clicking a done node expands its section: the scoreboard has ≤ 7 rows with the naive reference", async () => {
    mockApi(routes(journeyFixture("pronto")));
    renderEntrada();
    await screen.findByTestId("veredito");
    const models = card("competicao");
    fireEvent.click(within(models).getByRole("button", { name: /Recolher/ }));
    expect(screen.queryByTestId("placar")).not.toBeInTheDocument();
    expect(within(models).getByRole("button", { name: /Ver placar/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    fireEvent.click(within(stepNode("Competição de modelos")).getByRole("button"));
    const board = await screen.findByTestId("placar");
    const rows = board.querySelectorAll("li");
    expect(rows.length).toBeLessThanOrEqual(7);
    expect(rows).toHaveLength(7);
    expect(rows[0]).toHaveTextContent("Regressão");
    expect(rows[0]).toHaveTextContent(`85 séries · ${pct(85 / 220, 0)} · erro ${pct(0.134, 1)} onde venceu`);
    const ref = board.querySelector('[data-row="reference"]') as HTMLElement;
    expect(ref).toHaveTextContent("referência");
    expect(within(ref).getByRole("tooltip")).toHaveTextContent(REFERENCE_TOOLTIP);
    expect(rows[6]).toHaveTextContent("Outros 8 modelos");
    expect(rows[6]).toHaveTextContent("54 séries");
    expect(screen.getByTestId("padrao-insight")).toHaveTextContent(
      "Nas 66 séries sazonais, Regressão venceu 31 — cada padrão de demanda tem seu modelo.",
    );
    expect(screen.getByTestId("competicao-fatos")).toHaveTextContent(
      "15 modelos · 5,9 candidatos por série em média · executado em 4 min 54 s",
    );
    expect(screen.getByRole("link", { name: "Ver ranking completo" })).toHaveAttribute(
      "href",
      "/app/models?tab=ranking",
    );
  });

  it("?acao=carregar expands step 1 even when everything is ready", async () => {
    mockApi(routes(journeyFixture("pronto")));
    renderEntrada("/app/entrada?acao=carregar");
    expect(await screen.findByText("Usar base de demonstração")).toBeInTheDocument();
    expect(screen.getByTestId("dropzone")).toBeEnabled();
  });

  it("'Trocar base' expands step 1 from the collapsed summary", async () => {
    mockApi(routes(journeyFixture("pronto")));
    renderEntrada();
    await screen.findByTestId("veredito");
    expect(screen.queryByText("Usar base de demonstração")).not.toBeInTheDocument();
    expect(card("base")).toHaveTextContent("qualidade 100/100 (Excelente)");
    fireEvent.click(screen.getByRole("button", { name: "Trocar base" }));
    expect(screen.getByText("Usar base de demonstração")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Manter a base atual" }));
    expect(screen.queryByText("Usar base de demonstração")).not.toBeInTheDocument();
  });

  it("a non-trustworthy verdict keeps the report one click away, reading 'mesmo assim'", async () => {
    const tr = trustFixture();
    tr.verdict = {
      code: "nao_confiavel",
      label: "Não confiável — revise a base antes de decidir",
      headline:
        "O forecast acerta 60,0% fora da amostra, mas não supera o método ingênuo (72,7%) — revise a base e os modelos.",
      reasons: ["Viés de +12,0%: o forecast superestima a demanda."],
    };
    tr.gain_vs_naive_pp = -0.05;
    tr.run.fold_horizon = 1;
    mockApi(routes(journeyFixture("pronto"), { "/api/models/trust": tr }));
    renderEntrada();
    const verdict = await screen.findByTestId("veredito");
    expect(verdict).toHaveTextContent("Não confiável — revise a base antes de decidir");
    expect(verdict).toHaveTextContent("Viés de +12,0%: o forecast superestima a demanda.");
    expect(screen.getByTestId("abrir-relatorio")).toHaveTextContent("Abrir o relatório mesmo assim");
    expect(screen.getByTestId("abrir-relatorio")).toHaveAttribute("href", "/app/relatorio/resumo");
    expect(stepNode("Confiança no forecast")).toHaveTextContent("Não confiável");
    // fold horizon 1: no lead-time sentence
    expect(screen.queryByTestId("erro-por-antecedencia")).not.toBeInTheDocument();
  });

  it("a derived plan shows the amber 'estimados automaticamente' chip", async () => {
    mockApi(routes(journeyFixture("derived")));
    renderEntrada();
    await screen.findByTestId("veredito");
    const chip = screen.getByTestId("plano-chip");
    expect(chip).toHaveTextContent(
      "Orçamento e meta estimados automaticamente (ano anterior + 5%) — desvios vs orçamento são ilustrativos",
    );
  });

  it("without a completed run the trust endpoint's reason is shown", async () => {
    mockApi(routes(journeyFixture("pronto"), { "/api/models/trust": trustFixtures.indisponivel }));
    renderEntrada();
    expect(await screen.findAllByText("Ainda não há uma execução de forecast concluída.")).not.toHaveLength(
      0,
    );
  });

  it("a trust error stays inside its card; the other steps keep working", async () => {
    mockApi(
      routes(journeyFixture("pronto"), { "/api/models/trust": reply(501, { detail: "Em construção." }) }),
    );
    renderEntrada();
    expect(await screen.findAllByText("Em construção.")).not.toHaveLength(0);
    expect(card("base")).toHaveTextContent("Base validada");
    expect(screen.getByTestId("abrir-relatorio")).toHaveAttribute("href", "/app/relatorio/resumo");
  });

  it("the rerun banner appears while a new run is in progress", async () => {
    mockApi(routes(journeyFixture("rerunning")));
    renderEntrada();
    expect(await screen.findByText(/Nova execução em andamento \(63%\)/)).toBeInTheDocument();
    await screen.findByTestId("veredito");
  });
});

describe("Entrada · placar e antecedência", () => {
  it("with 7 winning models every one is shown by name (no 'Outros 1 modelo')", () => {
    const champions = trustFixture().champions.slice(0, 7);
    render(<ModelScoreboard champions={champions} />);
    const rows = screen.getByTestId("placar").querySelectorAll("li");
    expect(rows).toHaveLength(7);
    expect(screen.queryByText(/^Outros/)).not.toBeInTheDocument();
    expect(rows[6]).toHaveTextContent(champions[6].label);
  });

  it("the lead-time sentence uses the lags actually measured", () => {
    expect(
      lagSentence(
        [
          { lag: 2, wmape: 0.16 },
          { lag: 1, wmape: 0.13 },
          { lag: 3, wmape: 0.15 },
        ],
        3,
      ),
    ).toBe("O erro vai de 13,0% (1 mês de antecedência) a 15,0% (3 meses).");
    expect(
      lagSentence(
        [
          { lag: 1, wmape: 0.1 },
          { lag: 2, wmape: 0.12 },
        ],
        3,
      ),
    ).toBe("O erro vai de 10,0% (1 mês de antecedência) a 12,0% (2 meses).");
    expect(lagSentence([{ lag: 1, wmape: 0.1 }], 1)).toBeNull();
  });
});

describe("Entrada · layout rules", () => {
  it.each(["dados", "running", "failed", "pronto"] as const)(
    "no English UI terms on screen (%s)",
    async (state) => {
      mockApi(routes(journeyFixture(state)));
      renderEntrada();
      if (state === "pronto") await screen.findByTestId("veredito");
      else await waitFor(() => expect(card("competicao")).toBeInTheDocument());
      const text = document.body.textContent ?? "";
      for (const w of [
        "Budget",
        "Target",
        "Forecast error",
        "Loading",
        "Error",
        "Next",
        "Previous",
        "Revenue",
      ])
        expect(text, w).not.toMatch(new RegExp(`\\b${w}\\b`, "i"));
    },
  );

  it("no truncation, line clamp, side stripe or emoji in the Entrada sources", () => {
    const sources = import.meta.glob(["../components/entrada/*.{ts,tsx}", "../pages/Entrada.tsx"], {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>;
    expect(Object.keys(sources).length).toBeGreaterThanOrEqual(7);
    for (const [file, src] of Object.entries(sources)) {
      expect(src, file).not.toMatch(/\btruncate\b|line-clamp|border-l-/);
      expect(src, file).not.toMatch(/\p{Extended_Pictographic}/u);
    }
  });
});
