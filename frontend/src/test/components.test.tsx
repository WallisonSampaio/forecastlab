import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ClassBadge, KpiCard } from "../components/ui";
import { useFilters } from "../hooks/useFilters";

describe("UI components", () => {
  it("renders a KPI card with delta and hint", () => {
    render(
      <KpiCard label="Forecast Accuracy" value="91.6%" delta="+1.2%" deltaTone="good" hint="1 − WMAPE" />,
    );
    expect(screen.getByText("Forecast Accuracy")).toBeInTheDocument();
    expect(screen.getByText("91.6%")).toBeInTheDocument();
    expect(screen.getByText("+1.2%")).toHaveClass("text-emerald-700");
  });

  it("renders target classification badges with icon and label (never color alone)", () => {
    render(<ClassBadge value="AGGRESSIVE" />);
    expect(screen.getByText(/AGGRESSIVE/)).toBeInTheDocument();
    expect(screen.getByText("🔴")).toBeInTheDocument();
  });
});

describe("filter store", () => {
  it("sets and clears hierarchy filters", () => {
    act(() => useFilters.getState().setFilter("region", "South"));
    expect(useFilters.getState().filters).toEqual({ region: "South" });
    act(() => useFilters.getState().setFilter("region", undefined));
    expect(useFilters.getState().filters).toEqual({});
    act(() => useFilters.getState().setMeasure("units"));
    expect(useFilters.getState().measure).toBe("units");
  });
});
