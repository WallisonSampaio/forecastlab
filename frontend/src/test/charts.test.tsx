/**
 * IBCS chart kit (spec §5 F2 acceptance). jsdom has no canvas, so the ECharts-based charts are
 * tested through a mocked `EChart` that captures its props (`option`, `onClick`, `ariaLabel`);
 * the HTML charts (VarianceBars, CauseBars, FeasibilityRange) and the Drawer render for real.
 */
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BacktestLine } from "../charts/BacktestLine";
import { BridgeChart } from "../charts/BridgeChart";
import { CauseBars } from "../charts/CauseBars";
import { FeasibilityRange } from "../charts/FeasibilityRange";
import { VarianceBars } from "../charts/VarianceBars";
import { VarianceColumns } from "../charts/VarianceColumns";
import { Drawer } from "../components/Drawer";
import { Modal } from "../components/ui";
import { money, signedMoney, signedUnits } from "../lib/format";
import { FC_DECAL, IBCS, bridgeLayout, varianceText } from "../lib/ibcs";
import type {
  BridgeStep,
  CauseRow,
  ErrorRow,
  MonthlyErrorRow,
  MonthlyPlanRow,
  PlanRow,
} from "../types/deviations";

/* ------------------------------------------------------------- EChart mock */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Captured = { option: any; ariaLabel?: string; onClick?: (p: any) => void };
const echart = vi.hoisted(() => ({ calls: [] as Captured[] }));

vi.mock("../charts/EChart", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../charts/EChart")>();
  const { createElement } = await import("react");
  return {
    ...actual,
    EChart: (props: Captured) => {
      echart.calls.push(props);
      return createElement("div", { role: "img", "aria-label": props.ariaLabel, "data-testid": "echart" });
    },
  };
});

const last = () => echart.calls[echart.calls.length - 1];
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const seriesById = (option: any, id: string) => option.series.find((s: { id?: string }) => s.id === id);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const axes = (option: any) => [option.xAxis, option.yAxis].flat().filter(Boolean);

beforeEach(() => {
  echart.calls.length = 0;
});

/** Opens the "Ver tabela" view and returns the body rows of its table. */
function openTable() {
  fireEvent.click(screen.getByRole("button", { name: /^Ver tabela/ }));
  const table = screen.getByRole("table");
  return within(table).getAllByRole("row").slice(1); // drop the header row
}

/* ---------------------------------------------------------------- fixtures */

const step = (
  key: BridgeStep["key"],
  label: string,
  value: number,
  kind: BridgeStep["kind"],
  notation?: BridgeStep["notation"],
): BridgeStep => ({ key, label, value, kind, notation, help: `Definição de ${label.toLowerCase()}` });

const UNITS_BRIDGE: BridgeStep[] = [
  step("reference", "Orçamento", 1_200_000, "total", "PL"),
  step("volume", "Volume", -60_000, "delta"),
  step("events", "Eventos", 15_000, "delta"),
  step("compared", "Consenso", 1_155_000, "total", "FC"),
];

/** Realizado demo: totals ≈ 18× the largest step. */
const REVENUE_BRIDGE: BridgeStep[] = [
  step("reference", "Orçamento", 91_440_000, "total", "PL"),
  step("volume", "Volume", 3_670_000, "delta"),
  step("mix", "Mix", -2_260_000, "delta"),
  step("price", "Preço", -5_000_000, "delta"),
  step("compared", "Real", 87_850_000, "total", "AC"),
];

const months = Array.from({ length: 12 }, (_, i) => {
  const d = new Date(Date.UTC(2026, 9 + i, 1));
  return d.toISOString().slice(0, 10);
});

const PLAN_MONTHS: MonthlyPlanRow[] = months.map((date, i) => {
  const p = 8_000_000 + i * 100_000;
  const x = p + (i % 3 === 0 ? 250_000 : -400_000);
  return {
    date,
    x,
    p,
    py: p * 0.93,
    target: p * 1.08,
    low: x * 0.9,
    high: x * 1.1,
    variance: x - p,
    variance_pct: (x - p) / p,
  };
});

const ERROR_MONTHS: MonthlyErrorRow[] = months.map((date, i) => {
  const actual = 7_000_000 + i * 50_000;
  const forecast = actual + (i % 2 === 0 ? 300_000 : -200_000);
  return {
    date,
    actual,
    forecast,
    error: forecast - actual,
    abs_error: Math.abs(forecast - actual),
    wmape: 0.04,
  };
});

const LONG_NAME = "Rede Horizonte Supermercados · SKU-10101 Biscoito Integral 200g"; // 62 chars

const planRow = (key: string, variance: number, extra: Partial<PlanRow> = {}): PlanRow => ({
  key,
  label: key,
  x: 10_000_000 + variance,
  p: 10_000_000,
  variance,
  variance_pct: variance / 10_000_000,
  share_of_adverse: null,
  share_of_favorable: null,
  cum_share: null,
  prob_hit: 0.3,
  growth_plan: 0.08,
  growth_fc: 0.01,
  realized_variance_pct: null,
  effects: { volume: variance, mix: 0, price: 0, events: 0 },
  tags: [],
  is_exception: false,
  n_series: 4,
  drillable: true,
  ...extra,
});

const PLAN_ROWS: PlanRow[] = [
  planRow("Litoral Market", -1_580_000, {
    cum_share: 0.32,
    tags: [
      { code: "premissa_otimista", label: "Premissa otimista" },
      { code: "recorrente", label: "Recorrente" },
      { code: "terceira", label: "Terceira tag" },
    ],
  }),
  planRow(LONG_NAME, -1_380_000, { cum_share: 0.6, drillable: false }),
  planRow("Mercado Sol", -900_000, { cum_share: 0.78 }),
  planRow("ClickCesta", 420_000, { prob_hit: 0.71 }),
];

const errorRow = (key: string, abs: number, net: number, extra: Partial<ErrorRow> = {}): ErrorRow => ({
  key,
  label: key,
  actual: 5_000_000,
  forecast: 5_000_000 + net,
  abs_error: abs,
  net_error: net,
  wmape: 0.35,
  bias: net / 5_000_000,
  bias_class: net > 0 ? "Over" : "Under",
  systematic: Math.abs(net),
  noise: abs - Math.abs(net),
  share: 0.4,
  cum_share: 0.4,
  top_cause: null,
  is_exception: true,
  n_series: 3,
  drillable: true,
  ...extra,
});

const CAUSES: CauseRow[] = [
  {
    code: "volatilidade",
    label: "Volatilidade",
    group: "inherent",
    group_label: "Inerente",
    abs_error: 4_150_000,
    share: 0.27,
    net_error: 100_000,
    direction: "mixed",
    n_cells: 300,
    n_series: 80,
  },
  {
    code: "promocao",
    label: "Promoção não antecipada",
    group: "controllable",
    group_label: "Controlável",
    abs_error: 2_900_000,
    share: 0.19,
    net_error: -2_500_000,
    direction: "under",
    n_cells: 120,
    n_series: 60,
  },
  {
    code: "patamar",
    label: "Mudança de patamar",
    group: "controllable",
    group_label: "Controlável",
    abs_error: 1_700_000,
    share: 0.11,
    net_error: 1_500_000,
    direction: "over",
    n_cells: 40,
    n_series: 12,
  },
  {
    code: "sem_causa",
    label: "Sem causa identificada",
    group: "unexplained",
    group_label: "Sem causa",
    abs_error: 1_230_000,
    share: 0.08,
    net_error: 0,
    direction: "mixed",
    n_cells: 90,
    n_series: 50,
  },
];

/* ------------------------------------------------------------------ bridge */

describe("BridgeChart", () => {
  it("ponte em unidades: 4 categorias e 4 linhas na tabela", () => {
    render(<BridgeChart steps={UNITS_BRIDGE} measure="units" ariaLabel="Ponte em unidades" />);
    expect(screen.getByRole("img", { name: "Ponte em unidades" })).toBeInTheDocument();
    expect(last().option.xAxis.data).toEqual(["Orçamento", "Volume", "Eventos", "Consenso"]);
    expect(screen.getByText(/Em unidades não há efeito preço\/mix/)).toBeInTheDocument();
    const rows = openTable();
    expect(rows).toHaveLength(4);
    expect(within(rows[1]).getByText(signedUnits(-60_000))).toBeInTheDocument();
  });

  it("descarta preço e mix quando a medida é unidades", () => {
    const withPriceMix = [
      ...UNITS_BRIDGE.slice(0, 2),
      step("mix", "Mix", 0, "delta"),
      step("price", "Preço", 0, "delta"),
      ...UNITS_BRIDGE.slice(2),
    ];
    render(<BridgeChart steps={withPriceMix} measure="units" ariaLabel="Ponte" />);
    expect(last().option.xAxis.data).toHaveLength(4);
  });

  it("aplica a quebra de escala quando os totais dominam as etapas", () => {
    render(<BridgeChart steps={REVENUE_BRIDGE} measure="revenue" ariaLabel="Ponte U12M" />);
    const { option } = last();
    const marker = seriesById(option, "scale-break");
    expect(marker).toBeDefined();
    expect(marker.data).toHaveLength(2); // one cut per total bar
    expect(option.yAxis.min).toBeGreaterThan(0);
    expect(option.yAxis.min).toBeLessThan(91_440_000 - 3_670_000 - 2_260_000 - 5_000_000);
    expect(screen.getByText(/Escala interrompida/)).toBeInTheDocument();
  });

  it("sem quebra de escala quando as etapas são grandes", () => {
    const steps = [
      step("reference", "Orçamento", 10_000_000, "total", "PL"),
      step("volume", "Volume", -4_000_000, "delta"),
      step("compared", "Consenso", 6_000_000, "total", "FC"),
    ];
    render(<BridgeChart steps={steps} measure="revenue" ariaLabel="Ponte" />);
    expect(seriesById(last().option, "scale-break")).toBeUndefined();
    expect(last().option.yAxis.min).toBeUndefined();
    expect(bridgeLayout(steps).scaleBreak).toBe(false);
  });

  it("usa a notação IBCS, rótulos com sinal e sem eixo de valores", () => {
    render(<BridgeChart steps={REVENUE_BRIDGE} measure="revenue" ariaLabel="Ponte" />);
    const { option } = last();
    const data = seriesById(option, "bridge").data;
    // PL: white with ink outline · AC: solid ink
    expect(data[0].itemStyle).toMatchObject({ color: "#ffffff", borderColor: IBCS.ink, borderWidth: 1.5 });
    expect(data[4].itemStyle).toMatchObject({ color: IBCS.ink });
    // Δ: green above, red below, always signed
    expect(data[1].itemStyle.color).toBe(IBCS.good);
    expect(data[3].itemStyle.color).toBe(IBCS.bad);
    expect(data[1].label.formatter).toBe(signedMoney(3_670_000));
    expect(data[3].label.formatter).toBe(signedMoney(-5_000_000));
    expect(data[3].label.position).toBe("bottom");
    expect(option.yAxis.show).toBe(false);
    expect(option.legend).toBeUndefined();
  });

  it("FC usa o hachurado (decal) da notação", () => {
    render(<BridgeChart steps={UNITS_BRIDGE} measure="units" ariaLabel="Ponte" />);
    const fc = seriesById(last().option, "bridge").data[3];
    expect(fc.itemStyle.decal).toEqual(FC_DECAL);
  });

  it("clique numa etapa apenas destaca (sem mudar estado externo)", () => {
    render(<BridgeChart steps={REVENUE_BRIDGE} measure="revenue" ariaLabel="Ponte" />);
    act(() => last().onClick?.({ seriesId: "bridge", dataIndex: 3, name: "Preço" }));
    const data = seriesById(last().option, "bridge").data;
    expect(data[3].itemStyle.opacity).toBe(1);
    expect(data[0].itemStyle.opacity).toBeLessThan(1);
  });

  it("em painel estreito vira ponte horizontal: nomes à esquerda, valores à direita", () => {
    // The 8-step Meta bridge in the 5/12 "Por que desviou?" panel at 1366 px (~360 px wide).
    const original = globalThis.ResizeObserver;
    class WidthObserver {
      cb: ResizeObserverCallback;
      constructor(cb: ResizeObserverCallback) {
        this.cb = cb;
      }
      observe() {
        this.cb([{ contentRect: { width: 360 } } as ResizeObserverEntry], this as never);
      }
      unobserve() {}
      disconnect() {}
    }
    globalThis.ResizeObserver = WidthObserver as unknown as typeof ResizeObserver;
    try {
      const steps = [
        step("reference", "Meta", 106_000_000, "total", "TG"),
        step("challenge", "Desafio comercial", -7_610_000, "delta"),
        step("budget_subtotal", "Orçamento", 98_390_000, "subtotal", "PL"),
        step("volume", "Volume", -1_400_000, "delta"),
        step("mix", "Mix", -2_100_000, "delta"),
        step("price", "Preço", -710_000, "delta"),
        step("events", "Eventos comerciais", 130_000, "delta"),
        step("compared", "Consenso", 94_310_000, "total", "FC"),
      ];
      render(<BridgeChart steps={steps} measure="revenue" ariaLabel="Ponte da meta" />);
      const { option } = last();
      expect(option.yAxis).toMatchObject({ type: "category", inverse: true });
      expect(option.yAxis.data).toEqual(steps.map((s) => s.label));
      expect(option.yAxis.axisLabel.overflow).toBe("break");
      expect(option.xAxis).toMatchObject({ type: "value", show: false });
      const data = seriesById(option, "bridge").data;
      for (const d of data) expect(d.label.position).toBe("right");
      expect(data[1].label.formatter).toBe(signedMoney(-7_610_000));
      // the longest bar still leaves room for its value label
      expect(option.xAxis.max).toBeGreaterThan(106_000_000);
      expect(seriesById(option, "scale-break").data).toHaveLength(3); // Meta, Orçamento, Consenso
      expect(JSON.stringify(option)).not.toContain('"truncate"');
    } finally {
      globalThis.ResizeObserver = original;
    }
  });
});

/* --------------------------------------------------------- monthly variance */

describe("VarianceColumns", () => {
  it("modo plano: 12 meses, Δ com sinal, trimestres e tabela", () => {
    const onSelectMonth = vi.fn();
    const quarters = [0, 1, 2, 3].map((k) => ({
      label: `T${k + 1} · trimestre`,
      start: months[k * 3],
      end: months[k * 3 + 2],
      variance: -500_000,
    }));
    render(
      <VarianceColumns
        rows={PLAN_MONTHS}
        mode="plan"
        xKind="FC"
        xLabel="Consenso"
        pLabel="Orçamento"
        measure="revenue"
        quarters={quarters}
        onSelectMonth={onSelectMonth}
        ariaLabel="Consenso vs orçamento por mês"
      />,
    );
    const { option } = last();
    expect(option.xAxis[1].data).toHaveLength(12);
    const delta = seriesById(option, "delta");
    expect(delta.data[0].label.formatter.startsWith("+")).toBe(true);
    expect(delta.data[1].label.formatter.startsWith("-")).toBe(true);
    expect(delta.data[1].itemStyle.color).toBe(IBCS.bad);
    expect(seriesById(option, "front").data[0].itemStyle.decal).toEqual(FC_DECAL); // FC hatched
    expect(seriesById(option, "back").data[0].itemStyle.borderColor).toBe(IBCS.ink); // PL outline
    expect(seriesById(option, "front").markArea.data).toHaveLength(4);
    expect(seriesById(option, "target")).toBeDefined(); // Meta tick when targets exist

    // The click hands back the month as "YYYY-MM", ready for the URL `periodo`.
    act(() => last().onClick?.({ dataIndex: 2, name: months[2] }));
    expect(onSelectMonth).toHaveBeenLastCalledWith("2026-12");

    const rows = openTable();
    expect(rows).toHaveLength(12);
    expect(within(rows[1]).getByText(varianceText(-400_000, "revenue"))).toBeInTheDocument();
    fireEvent.click(within(rows[3]).getByRole("button", { name: "jan/2027" }));
    expect(onSelectMonth).toHaveBeenLastCalledWith("2027-01");
  });

  it("modo erro: Real sólido vs previsto hachurado e erro vermelho/azul", () => {
    render(
      <VarianceColumns
        rows={ERROR_MONTHS}
        mode="error"
        xLabel="Estatístico"
        measure="revenue"
        ariaLabel="Erro por mês"
      />,
    );
    const { option } = last();
    expect(seriesById(option, "front").name).toBe("Real");
    expect(seriesById(option, "front").data[0].itemStyle.color).toBe(IBCS.ink);
    expect(seriesById(option, "back").data[0].itemStyle.decal).toEqual(FC_DECAL);
    const delta = seriesById(option, "delta");
    expect(delta.data[0].itemStyle.color).toBe(IBCS.over);
    expect(delta.data[1].itemStyle.color).toBe(IBCS.under);
    expect(openTable()).toHaveLength(12);
    expect(screen.getAllByText(/superestimou/).length).toBeGreaterThan(0);
  });

  it("realça o mês selecionado", () => {
    render(
      <VarianceColumns
        rows={PLAN_MONTHS}
        mode="plan"
        xLabel="Real"
        xKind="AC"
        pLabel="Orçamento"
        measure="revenue"
        selectedMonth={months[5]}
        ariaLabel="Real vs orçamento"
      />,
    );
    const front = seriesById(last().option, "front").data;
    expect(front[5].itemStyle.opacity).toBe(1);
    expect(front[4].itemStyle.opacity).toBeLessThan(1);
  });

  it("aceita o mês da URL (YYYY-MM) como seleção", () => {
    render(
      <VarianceColumns
        rows={PLAN_MONTHS}
        mode="plan"
        xLabel="Consenso"
        pLabel="Orçamento"
        measure="revenue"
        selectedMonth={months[5].slice(0, 7)}
        onSelectMonth={vi.fn()}
        ariaLabel="Consenso vs orçamento"
      />,
    );
    const front = seriesById(last().option, "front").data;
    expect(front[5].itemStyle.opacity).toBe(1);
    expect(front[0].itemStyle.opacity).toBeLessThan(1);
    const rows = openTable();
    expect(within(rows[5]).getByRole("button")).toHaveAttribute("aria-pressed", "true");
    expect(within(rows[0]).getByRole("button")).toHaveAttribute("aria-pressed", "false");
  });
});

/* ----------------------------------------------------------------- backtest */

describe("BacktestLine", () => {
  it("três linhas com rótulo direto no fim, sem legenda e sem grade", () => {
    const rows = ERROR_MONTHS.map((r) => ({
      date: r.date,
      actual: r.actual,
      statistical: r.forecast,
      naive: r.actual * 1.2,
    }));
    render(<BacktestLine rows={rows} ariaLabel="Real vs previsto fora da amostra" />);
    const { option } = last();
    expect(option.series.map((s: { name: string }) => s.name)).toEqual(["Real", "Estatístico", "Ingênuo"]);
    for (const s of option.series) expect(s.endLabel.show).toBe(true);
    expect(option.series[0].lineStyle).toMatchObject({ width: 2.4, type: "solid" });
    expect(option.series[1].lineStyle.type).toBe("dashed");
    expect(option.series[2].lineStyle.type).toBe("dotted");
    expect(option.legend).toBeUndefined();
    expect(openTable()).toHaveLength(12);
  });
});

/* ------------------------------------------------- shared chart declutter rules */

describe("regras de declutter dos gráficos ECharts", () => {
  it("nenhum eixo usa overflow truncate e nenhum desenha grade", () => {
    render(
      <>
        <BridgeChart steps={REVENUE_BRIDGE} measure="revenue" ariaLabel="a" />
        <BridgeChart steps={UNITS_BRIDGE} measure="units" ariaLabel="b" />
        <VarianceColumns rows={PLAN_MONTHS} mode="plan" xLabel="Consenso" measure="revenue" ariaLabel="c" />
        <VarianceColumns
          rows={ERROR_MONTHS}
          mode="error"
          xLabel="Estatístico"
          measure="revenue"
          ariaLabel="d"
        />
        <BacktestLine
          rows={ERROR_MONTHS.map((r) => ({
            date: r.date,
            actual: r.actual,
            statistical: r.forecast,
            naive: 1,
          }))}
          ariaLabel="e"
        />
      </>,
    );
    expect(echart.calls.length).toBeGreaterThanOrEqual(5);
    for (const { option, ariaLabel } of echart.calls) {
      expect(ariaLabel).toBeTruthy();
      for (const axis of axes(option)) {
        expect(axis.axisLabel?.overflow).not.toBe("truncate");
        expect(axis.splitLine?.show ?? false).toBe(false);
      }
      expect(JSON.stringify(option)).not.toContain('"truncate"');
    }
    // every chart offers the table alternative
    expect(screen.getAllByRole("button", { name: /^Ver tabela/ })).toHaveLength(5);
  });
});

/* ------------------------------------------------------------ variance bars */

describe("VarianceBars", () => {
  it("linhas são botões com aria-pressed; nomes longos quebram linha (sem truncate)", () => {
    const onSelect = vi.fn();
    const { container } = render(
      <VarianceBars
        rows={PLAN_ROWS}
        mode="plan"
        measure="revenue"
        others={{ n: 5, value: -120_000 }}
        selectedKey="Litoral Market"
        onSelect={onSelect}
        onDrill={vi.fn()}
        ariaLabel="Onde está o desvio?"
      />,
    );
    const list = screen.getByRole("list", { name: "Onde está o desvio?" });
    const rowButtons = within(list)
      .getAllByRole("button")
      .filter((b) => b.hasAttribute("aria-pressed"));
    expect(rowButtons).toHaveLength(4);
    expect(rowButtons[0]).toHaveAttribute("aria-pressed", "true");
    expect(rowButtons[1]).toHaveAttribute("aria-pressed", "false");

    expect(LONG_NAME.length).toBeGreaterThanOrEqual(60);
    const name = screen.getByText(LONG_NAME);
    expect(name.className).toContain("break-words");
    expect(container.querySelector('[class*="truncate"], [class*="line-clamp"]')).toBeNull();
    // Tag chips (backend labels such as "Premissa de crescimento otimista") wrap on their own line
    // under the name and bar, never running over the bar.
    const chip = screen.getByText("Premissa otimista");
    expect(chip.className).not.toContain("whitespace-nowrap");
    expect(chip.parentElement?.className).toContain("col-span-2");

    fireEvent.click(rowButtons[2]);
    expect(onSelect).toHaveBeenCalledWith("Mercado Sol");
  });

  it("desvio sempre com sinal e a palavra acima/abaixo; ≤ 2 tags; Pareto e 'Demais'", () => {
    render(
      <VarianceBars
        rows={PLAN_ROWS}
        mode="plan"
        measure="revenue"
        others={{ n: 5, value: -120_000 }}
        ariaLabel="Gap por cliente"
      />,
    );
    expect(screen.getByText(varianceText(-1_580_000, "revenue"))).toBeInTheDocument();
    expect(screen.getByText(varianceText(420_000, "revenue"))).toBeInTheDocument();
    expect(varianceText(-1_580_000, "revenue")).toMatch(/^-R\$ .* abaixo$/);
    expect(varianceText(420_000, "revenue")).toMatch(/^\+R\$ .* acima$/);
    expect(screen.getByText("Premissa otimista")).toBeInTheDocument();
    expect(screen.queryByText("Terceira tag")).toBeNull();
    expect(screen.getByText("32% acum.")).toBeInTheDocument();
    expect(screen.getAllByText("30% de chance")).toHaveLength(3);
    expect(screen.getByText("71% de chance")).toBeInTheDocument();
    // dashed line right after the row where the adverse cumulative share reaches 50%
    expect(screen.getByText(/estes 2 concentram metade das perdas/)).toBeInTheDocument();
    expect(screen.getByText("Demais (5)")).toBeInTheDocument();

    const rows = openTable();
    expect(rows).toHaveLength(PLAN_ROWS.length + 1);
  });

  it("detalhar: botão ›, duplo clique ou Shift+Enter; desabilitado quando não detalhável", () => {
    const onDrill = vi.fn();
    const onSelect = vi.fn();
    render(
      <VarianceBars
        rows={PLAN_ROWS}
        mode="plan"
        measure="revenue"
        onSelect={onSelect}
        onDrill={onDrill}
        ariaLabel="Onde"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Detalhar Litoral Market" }));
    expect(onDrill).toHaveBeenLastCalledWith("Litoral Market");
    expect(screen.getByRole("button", { name: `Detalhar ${LONG_NAME}` })).toBeDisabled();

    const list = screen.getByRole("list", { name: "Onde" });
    const rows = within(list)
      .getAllByRole("button")
      .filter((b) => b.hasAttribute("aria-pressed"));
    fireEvent.keyDown(rows[2], { key: "Enter", shiftKey: true });
    expect(onDrill).toHaveBeenLastCalledWith("Mercado Sol");
    fireEvent.doubleClick(rows[3]);
    expect(onDrill).toHaveBeenLastCalledWith("ClickCesta");
    // not drillable: Shift+Enter does nothing
    onDrill.mockClear();
    fireEvent.keyDown(rows[1], { key: "Enter", shiftKey: true });
    expect(onDrill).not.toHaveBeenCalled();
    expect(screen.getByText(/Clique para focar/)).toBeInTheDocument();
  });

  it("modo erro: sistemático + ruído, WMAPE e viés", () => {
    render(
      <VarianceBars
        rows={[errorRow("Litoral Market", 1_200_000, 700_000), errorRow("Mercado Sol", 800_000, -500_000)]}
        mode="error"
        measure="revenue"
        onSelect={vi.fn()}
        ariaLabel="Onde o forecast errou?"
      />,
    );
    expect(screen.getAllByText("WMAPE 35,0%")).toHaveLength(2);
    expect(screen.getByText("Superestimado")).toBeInTheDocument();
    expect(screen.getByText("Subestimado")).toBeInTheDocument();
    expect(screen.getByText(money(1_200_000))).toBeInTheDocument();
    expect(screen.getByText(/40% do erro · superestimou/)).toBeInTheDocument();
    expect(openTable()).toHaveLength(2);
  });

  it("mais de 12 membros: mostra 12 e agrupa o resto em 'Demais'", () => {
    const many = Array.from({ length: 15 }, (_, i) => planRow(`Cliente ${i + 1}`, -(15 - i) * 10_000));
    render(<VarianceBars rows={many} mode="plan" measure="revenue" onSelect={vi.fn()} ariaLabel="Muitos" />);
    const list = screen.getByRole("list", { name: "Muitos" });
    expect(within(list).getAllByRole("button")).toHaveLength(12);
    expect(screen.getByText("Demais (3)")).toBeInTheDocument();
  });
});

/* ---------------------------------------------------------------- cause bars */

describe("CauseBars", () => {
  it("agrupa em Controlável / Inerente / Sem causa e alterna a seleção", () => {
    const onSelect = vi.fn();
    render(<CauseBars causes={CAUSES} selected="promocao" onSelect={onSelect} ariaLabel="Por que errou?" />);
    const group = screen.getByRole("group", { name: "Por que errou?" });
    const headers = within(group)
      .getAllByText(/^(Controlável|Inerente|Sem causa)$/)
      .map((h) => h.textContent);
    expect(headers).toEqual(["Controlável", "Inerente", "Sem causa"]);
    expect(screen.getByText("30% do erro · R$ 4,60 mi")).toBeInTheDocument(); // 19% + 11%

    const promo = screen.getByRole("button", { name: /Promoção não antecipada/ });
    expect(promo).toHaveAttribute("aria-pressed", "true");
    expect(within(promo).getByText("subestimou")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Volatilidade/ }));
    expect(onSelect).toHaveBeenCalledWith("volatilidade");

    expect(openTable()).toHaveLength(CAUSES.length);
  });

  it("sem onSelect, as linhas não são botões; a nota do capítulo aparece abaixo", () => {
    render(<CauseBars causes={CAUSES} ariaLabel="Causas" note="Erro fora da amostra (backtest)." />);
    expect(screen.queryByRole("button", { name: /Volatilidade/ })).toBeNull();
    expect(screen.getByText("Volatilidade")).toBeInTheDocument();
    expect(screen.getByText("Erro fora da amostra (backtest).")).toBeInTheDocument();
  });
});

/* ---------------------------------------------------------- feasibility range */

describe("FeasibilityRange", () => {
  const a = { p10: 88e6, p50: 94.3e6, p90: 100.6e6, target: 106e6, budget: 98.39e6 };

  it("tem nome acessível e tabela com um marcador por linha", () => {
    render(<FeasibilityRange a={a} f={money} />);
    expect(
      screen.getByRole("img", { name: /Faixa provável P10–P90.*meta R\$ 106,00 mi/ }),
    ).toBeInTheDocument();
    const rows = openTable();
    expect(rows).toHaveLength(5);
    expect(within(rows[4]).getByText(money(106e6))).toBeInTheDocument();
  });

  it("sem orçamento, o marcador sai da escala e da tabela", () => {
    render(<FeasibilityRange a={{ ...a, budget: 0 }} f={money} ariaLabel="Viabilidade da meta" />);
    expect(screen.getByRole("img", { name: "Viabilidade da meta" })).toBeInTheDocument();
    expect(openTable()).toHaveLength(4);
  });
});

/* -------------------------------------------------------------------- drawer */

function DrawerHarness({ onClose }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Abrir ficha
      </button>
      <Drawer
        open={open}
        title="Litoral Market · SKU-10101"
        onClose={() => {
          onClose?.();
          setOpen(false);
        }}
        footer={<button type="button">Abrir no workspace</button>}
      >
        <a href="#evidencias">Evidências</a>
        <div role="dialog" aria-label="Interno">
          <button type="button">Botão interno</button>
        </div>
      </Drawer>
    </>
  );
}

describe("Drawer", () => {
  it("é um diálogo modal rotulado pelo título, com foco inicial dentro", () => {
    render(<DrawerHarness />);
    fireEvent.click(screen.getByRole("button", { name: "Abrir ficha" }));
    const dialog = screen.getByRole("dialog", { name: "Litoral Market · SKU-10101" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog.style.width).toBe("560px");
    expect(screen.getByRole("button", { name: "Fechar" })).toHaveFocus();
  });

  it("prende o foco (Tab e Shift+Tab circulam dentro da gaveta)", () => {
    render(<DrawerHarness />);
    fireEvent.click(screen.getByRole("button", { name: "Abrir ficha" }));
    const close = screen.getByRole("button", { name: "Fechar" });
    const lastItem = screen.getByRole("button", { name: "Abrir no workspace" });
    lastItem.focus();
    fireEvent.keyDown(lastItem, { key: "Tab" });
    expect(close).toHaveFocus();
    fireEvent.keyDown(close, { key: "Tab", shiftKey: true });
    expect(lastItem).toHaveFocus();
    // focus that escaped the sheet is pulled back in
    screen.getByRole("button", { name: "Abrir ficha" }).focus();
    fireEvent.keyDown(document.activeElement!, { key: "Tab" });
    expect(close).toHaveFocus();
  });

  it("Esc fecha e devolve o foco a quem abriu; Esc num diálogo interno é dele", () => {
    const onClose = vi.fn();
    render(<DrawerHarness onClose={onClose} />);
    const opener = screen.getByRole("button", { name: "Abrir ficha" });
    opener.focus();
    fireEvent.click(opener);

    fireEvent.keyDown(screen.getByRole("button", { name: "Botão interno" }), { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.keyDown(screen.getByRole("button", { name: "Fechar" }), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog", { name: "Litoral Market · SKU-10101" })).toBeNull();
    expect(opener).toHaveFocus();
  });

  it("um Modal aberto pela gaveta recebe o foco e Esc fecha só o Modal", () => {
    const closeDrawer = vi.fn();
    function Harness() {
      const [modal, setModal] = useState(false);
      return (
        <Drawer
          open
          title="Ficha da série"
          onClose={closeDrawer}
          footer={
            <button type="button" onClick={() => setModal(true)}>
              Criar ajuste comercial
            </button>
          }
        >
          <p>Evidências</p>
          <Modal open={modal} title="Novo ajuste comercial" onClose={() => setModal(false)}>
            <input aria-label="Uplift" />
          </Modal>
        </Drawer>
      );
    }
    render(<Harness />);
    const create = screen.getByRole("button", { name: "Criar ajuste comercial" });
    create.focus();
    fireEvent.click(create);
    const modal = screen.getByRole("dialog", { name: "Novo ajuste comercial" });
    expect(modal).toHaveFocus();

    // Esc pressed while focus is still on the sheet's button: only the modal closes.
    create.focus();
    fireEvent.keyDown(create, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Novo ajuste comercial" })).toBeNull();
    expect(closeDrawer).not.toHaveBeenCalled();
    expect(create).toHaveFocus();
    // With the modal gone, Esc closes the sheet again.
    fireEvent.keyDown(create, { key: "Escape" });
    expect(closeDrawer).toHaveBeenCalledTimes(1);
  });
});
