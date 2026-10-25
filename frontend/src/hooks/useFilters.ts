import { create } from "zustand";

import type { Measure } from "../lib/format";
import type { Filters } from "../types";

export const FILTER_DIMS = ["region", "channel", "customer", "category", "brand", "sku"] as const;
export type FilterDim = (typeof FILTER_DIMS)[number];

interface FilterState {
  filters: Filters;
  measure: Measure;
  setFilter: (dim: FilterDim, value: string | undefined) => void;
  setFilters: (f: Filters) => void;
  clear: () => void;
  setMeasure: (m: Measure) => void;
}

export const useFilters = create<FilterState>((set) => ({
  filters: {},
  measure: "revenue",
  setFilter: (dim, value) =>
    set((s) => {
      const next = { ...s.filters };
      if (value) next[dim] = value;
      else delete next[dim];
      return { filters: next };
    }),
  setFilters: (f) => set({ filters: f }),
  clear: () => set({ filters: {} }),
  setMeasure: (m) => set({ measure: m }),
}));

export const activeFilterCount = (f: Filters) => Object.values(f).filter(Boolean).length;
