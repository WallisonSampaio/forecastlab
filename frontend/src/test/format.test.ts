import { describe, expect, it } from "vitest";

import {
  aboveBelow,
  compact,
  formatKpi,
  formatValue,
  lagLabel,
  monthLabel,
  money,
  pct,
  pp,
  shortMonth,
  signedMeasure,
  signedMoney,
  signedUnits,
  type KpiFormat,
} from "../lib/format";
import { shortNumber, shortSigned, varianceText } from "../lib/ibcs";
import { t } from "../lib/labels";
import { buildQuery } from "../services/api";

describe("formatação pt-BR", () => {
  it("compacta números grandes", () => {
    expect(compact(1_234)).toBe("1.234");
    expect(compact(45_600)).toBe("45,6 mil");
    expect(compact(12_340_000)).toBe("12,34 mi");
    expect(compact(-2_500_000)).toBe("-2,50 mi");
    expect(compact(null)).toBe("—");
  });

  it("formata moeda e percentuais", () => {
    expect(money(94_300_000)).toBe("R$ 94,30 mi");
    expect(money(-4_090_000)).toBe("-R$ 4,09 mi");
    expect(pct(0.0842)).toBe("8,4%");
    expect(pct(0.012, 1, true)).toBe("+1,2%");
    expect(pct(-0.05, 0, true)).toBe("-5%");
  });

  it("formata pelo tipo de valor", () => {
    expect(formatValue(0.25, "percent")).toBe("25,0%");
    expect(formatValue(1500000, "currency")).toBe("R$ 1,50 mi");
    expect(formatValue("ETS", "text")).toBe("ETS");
    expect(formatValue(undefined, "units")).toBe("—");
  });

  it("rotula meses em português", () => {
    expect(shortMonth("2026-12-01")).toBe("dez/26");
    expect(monthLabel("2026-12-01")).toBe("dez/2026");
    expect(monthLabel("2026-12-01", "long")).toBe("dezembro de 2026");
  });
});

describe("helpers da jornada (sinal, p.p., KPI, antecedência)", () => {
  it("moeda com sinal explícito", () => {
    expect(signedMoney(420_000)).toBe("+R$ 420,0 mil");
    expect(signedMoney(4_090_000)).toBe("+R$ 4,09 mi");
    expect(signedMoney(-4_090_000)).toBe("-R$ 4,09 mi");
    expect(signedMoney(0)).toBe("R$ 0");
    expect(signedMoney(null)).toBe("—");
    expect(signedUnits(12_500)).toBe("+12,5 mil");
    expect(signedMeasure(-850, "units")).toBe("-850");
    expect(signedMeasure(1_500_000, "revenue")).toBe("+R$ 1,50 mi");
  });

  it("acima/abaixo sempre com sinal", () => {
    expect(aboveBelow(-1)).toBe("abaixo");
    expect(aboveBelow(2)).toBe("acima");
    expect(varianceText(-1_580_000, "revenue")).toBe("-R$ 1,58 mi abaixo");
    expect(varianceText(420_000, "revenue")).toBe("+R$ 420,0 mil acima");
  });

  it("pontos percentuais", () => {
    expect(pp(0.125)).toBe("12,5 p.p.");
    expect(pp(-0.02)).toBe("-2,0 p.p.");
    expect(pp(0.011, 1, true)).toBe("+1,1 p.p.");
    expect(pp(-0.0001, 1, true)).toBe("0,0 p.p.");
    expect(pp(undefined)).toBe("—");
  });

  it("formatKpi cobre todos os formatos de KpiSpec", () => {
    const cases: [KpiFormat, number | null, string | null, string][] = [
      ["currency", 94_300_000, null, "R$ 94,30 mi"],
      ["currency_signed", -4_090_000, null, "-R$ 4,09 mi"],
      ["currency_signed", 420_000, null, "+R$ 420,0 mil"],
      ["units", 45_600, null, "45,6 mil"],
      ["percent", 0.852, null, "85,2%"],
      ["percent_signed", -0.033, null, "-3,3%"],
      ["percent_signed", 0.072, null, "+7,2%"],
      ["pp", 0.011, null, "+1,1 p.p."],
      ["pp", -0.126, null, "-12,6 p.p."],
      ["text", null, "2 de 14 clientes", "2 de 14 clientes"],
      ["text", 3, null, "3"],
      ["currency", null, null, "—"],
      ["percent", null, "sem dados", "sem dados"],
    ];
    for (const [format, value, text, expected] of cases) {
      expect(formatKpi({ format, value, text })).toBe(expected);
    }
    // Probabilities ("Chance de …", ids prob_*) are whole percentages, as in the headlines.
    expect(formatKpi({ id: "prob_target", format: "percent", value: 0.2904 })).toBe("29%");
    expect(formatKpi({ id: "prob_hit", format: "percent", value: 0.4235 })).toBe("42%");
    expect(formatKpi({ id: "accuracy", format: "percent", value: 0.852 })).toBe("85,2%");
  });

  it("antecedência do backtest", () => {
    expect(lagLabel(3)).toBe("1–3 meses");
    expect(lagLabel(6)).toBe("1–6 meses");
    expect(lagLabel(1)).toBe("1 mês");
    expect(lagLabel(null)).toBe("1 mês");
  });

  it("rótulos curtos dos gráficos", () => {
    expect(shortNumber(8_120_000)).toBe("8,1 mi");
    expect(shortNumber(650_400)).toBe("650 mil");
    expect(shortNumber(1_234)).toBe("1.234");
    expect(shortSigned(250_000)).toBe("+250 mil");
    expect(shortSigned(-1_650_000)).toBe("-1,7 mi");
  });
});

describe("rótulos traduzidos", () => {
  it("traduz códigos da API e preserva valores desconhecidos", () => {
    expect(t.seriesType("Seasonal")).toBe("Sazonal");
    expect(t.classification("AGGRESSIVE")).toBe("Agressiva");
    expect(t.model("Moving Average")).toBe("Média Móvel");
    expect(t.event("Promoção")).toBe("Promoção");
    expect(t.confidence(null)).toBe("—");
    expect(t.causeGroup("controllable")).toBe("Controlável");
    expect(t.errorDirection("under")).toBe("Subestimou");
    expect(t.notation("PL")).toBe("Orçamento");
    expect(t.dimension("series_type")).toBe("Padrão de demanda");
  });
});

describe("api query builder", () => {
  it("repeats array params and skips empty values", () => {
    expect(buildQuery({ region: ["South", "North"], sku: undefined, measure: "units", empty: "" })).toBe(
      "?region=South&region=North&measure=units",
    );
    expect(buildQuery()).toBe("");
  });
});
