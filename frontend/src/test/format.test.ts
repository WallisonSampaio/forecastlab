import { describe, expect, it } from "vitest";

import { compact, formatValue, money, pct, shortMonth } from "../lib/format";
import { buildQuery } from "../services/api";

describe("format helpers", () => {
  it("compacts large numbers", () => {
    expect(compact(1_234)).toBe("1,234");
    expect(compact(45_600)).toBe("45.6K");
    expect(compact(12_340_000)).toBe("12.34M");
    expect(compact(-2_500_000)).toBe("-2.50M");
    expect(compact(null)).toBe("—");
  });

  it("formats money and percentages", () => {
    expect(money(94_300_000)).toBe("R$ 94.30M");
    expect(pct(0.0842)).toBe("8.4%");
    expect(pct(0.012, 1, true)).toBe("+1.2%");
    expect(pct(-0.05, 0, true)).toBe("-5%");
  });

  it("dispatches by value format", () => {
    expect(formatValue(0.25, "percent")).toBe("25.0%");
    expect(formatValue(1500000, "currency")).toBe("R$ 1.50M");
    expect(formatValue("ETS", "text")).toBe("ETS");
    expect(formatValue(undefined, "units")).toBe("—");
  });

  it("labels months", () => {
    expect(shortMonth("2026-12-01")).toBe("Dec 26");
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
