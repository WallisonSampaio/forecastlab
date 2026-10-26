import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataTable } from "../components/DataTable";
import { BiasBadge, Card, ChartFrame, ClassBadge, KpiCard, SeverityBadge } from "../components/ui";
import { useFilters } from "../hooks/useFilters";

const EMOJI = /\p{Extended_Pictographic}/u;

describe("componentes de UI", () => {
  it("renderiza o card de KPI com variação e dica", () => {
    render(
      <KpiCard label="Acurácia do forecast" value="91,6%" delta="+1,2%" deltaTone="good" hint="1 − WMAPE" />,
    );
    expect(screen.getByText("Acurácia do forecast")).toBeInTheDocument();
    expect(screen.getByText("91,6%")).toBeInTheDocument();
    expect(screen.getByText("+1,2%").closest("span")).toHaveClass("text-emerald-700");
  });

  it("o rótulo do KPI quebra linha livremente (sem line-clamp)", () => {
    const label = "Receita prevista com confiança alta nos próximos doze meses do ciclo";
    render(<KpiCard label={label} value="69%" />);
    const el = screen.getByText(label);
    expect(el.className).not.toMatch(/line-clamp|truncate/);
    expect(el).toHaveClass("break-words");
  });

  it("classificação da meta: ícone svg e rótulo (nunca só cor, sem emoji)", () => {
    for (const [code, label] of [
      ["REALISTIC", "Realista"],
      ["STRETCH", "Desafiadora"],
      ["AGGRESSIVE", "Agressiva"],
      ["UNDERESTIMATED", "Subestimada"],
    ]) {
      const { unmount } = render(<ClassBadge value={code} />);
      const badge = screen.getByText(label);
      expect(badge.querySelector("svg")).not.toBeNull();
      expect(badge.textContent).not.toMatch(EMOJI);
      unmount();
    }
  });

  it("viés: seta para cima, para baixo ou check, mais o rótulo", () => {
    for (const [code, label] of [
      ["Over", "Superestimado"],
      ["Under", "Subestimado"],
      ["Balanced", "Equilibrado"],
    ]) {
      const { unmount } = render(<BiasBadge value={code} />);
      const badge = screen.getByText(label);
      expect(badge.querySelector("svg")).not.toBeNull();
      expect(badge.textContent).not.toMatch(EMOJI);
      unmount();
    }
  });

  it("o Card leva data-visual e data-question até o DOM (orçamento visual da jornada)", () => {
    const { container } = render(
      <Card title="Onde está o desvio?" data-visual="onde" data-question="Onde está o desvio?">
        <div>conteúdo</div>
      </Card>,
    );
    const block = container.querySelector("[data-visual]");
    expect(block?.tagName).toBe("SECTION");
    expect(block).toHaveAttribute("data-visual", "onde");
    expect(block).toHaveAttribute("data-question", "Onde está o desvio?");
    expect(block).toHaveClass("card");
  });

  it("traduz a severidade", () => {
    render(<SeverityBadge value="high" />);
    expect(screen.getByText("Alto")).toBeInTheDocument();
  });

  it("ChartFrame alterna entre gráfico e tabela", () => {
    render(
      <ChartFrame
        ariaLabel="Receita por mês"
        columns={[{ label: "Mês" }, { label: "Valor", align: "right" }]}
        rows={[
          { key: "a", cells: ["out/2026", "R$ 1,00 mi"] },
          { key: "b", cells: ["nov/2026", "R$ 2,00 mi"] },
        ]}
      >
        <div>gráfico</div>
      </ChartFrame>,
    );
    const toggle = screen.getByRole("button", { name: "Ver tabela: Receita por mês" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    const table = screen.getByRole("table", { name: "Receita por mês" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getByRole("columnheader", { name: "Valor" })).toHaveClass("text-right");
    expect(screen.queryByText("gráfico")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Ver gráfico: Receita por mês" }));
    expect(screen.getByText("gráfico")).toBeInTheDocument();
  });
});

describe("DataTable", () => {
  const rows = [
    { name: "Litoral Market", value: 3 },
    { name: "ClickCesta", value: 10 },
  ];

  it("alinha cabeçalho e células numéricas à direita e ordena pelo teclado", () => {
    render(
      <DataTable
        rows={rows}
        dense
        columns={[
          { key: "name", label: "Cliente", wrap: true },
          { key: "value", label: "Valor", align: "right", format: "number" },
        ]}
      />,
    );
    const header = screen.getByRole("columnheader", { name: /Valor/ });
    expect(header).toHaveClass("text-right");
    expect(screen.getByText("10").closest("td")).toHaveClass("text-right");
    expect(screen.getByText("Litoral Market").closest("td")).toHaveClass("whitespace-normal");
    expect(screen.getByRole("table")).toHaveClass("[&_td]:py-1.5");

    fireEvent.keyDown(header, { key: "Enter" });
    expect(header).toHaveAttribute("aria-sort", "descending");
    const body = screen.getAllByRole("row").slice(1);
    expect(within(body[0]).getByText("ClickCesta")).toBeInTheDocument();
    fireEvent.click(header);
    expect(header).toHaveAttribute("aria-sort", "ascending");
  });
});

describe("filter store", () => {
  it("sets and clears hierarchy filters", () => {
    act(() => useFilters.getState().setFilter("region", "Sul"));
    expect(useFilters.getState().filters).toEqual({ region: "Sul" });
    act(() => useFilters.getState().setFilter("region", undefined));
    expect(useFilters.getState().filters).toEqual({});
    act(() => useFilters.getState().setMeasure("units"));
    expect(useFilters.getState().measure).toBe("units");
  });
});
