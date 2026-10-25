import { FilterX, SlidersHorizontal } from "lucide-react";
import { useMemo } from "react";

import { useGet } from "../hooks/useApi";
import { activeFilterCount, useFilters, type FilterDim } from "../hooks/useFilters";
import type { Measure } from "../lib/format";
import { Segmented } from "./ui";

export interface Dimensions {
  region: string[];
  channel: string[];
  customer: string[];
  category: string[];
  brand: string[];
  sku: { sku: string; product: string; category: string; brand: string }[];
  customers: { customer: string; region: string; channel: string; customer_location: string }[];
  series: { series_id: string; customer: string; sku: string; product: string }[];
  last_actual: string;
  horizon: string[];
}

export function useDimensions() {
  return useGet<Dimensions>("/api/data/dimensions", undefined, { staleTime: 60_000 });
}

const LABELS: Record<FilterDim, string> = {
  region: "Region",
  channel: "Channel",
  customer: "Customer",
  category: "Category",
  brand: "Brand",
  sku: "SKU",
};

const PLURAL: Record<FilterDim, string> = {
  region: "regions",
  channel: "channels",
  customer: "customers",
  category: "categories",
  brand: "brands",
  sku: "SKUs",
};

export function FilterBar({
  dims = ["region", "channel", "customer", "category", "brand", "sku"],
  showMeasure = true,
}: {
  dims?: FilterDim[];
  showMeasure?: boolean;
}) {
  const { data } = useDimensions();
  const { filters, setFilter, clear, measure, setMeasure } = useFilters();

  const options = useMemo(() => {
    if (!data) return {} as Record<FilterDim, { value: string; label: string }[]>;
    const customers = data.customers.filter(
      (c) =>
        (!filters.region || c.region === filters.region) &&
        (!filters.channel || c.channel === filters.channel),
    );
    const skus = data.sku.filter(
      (s) =>
        (!filters.category || s.category === filters.category) &&
        (!filters.brand || s.brand === filters.brand),
    );
    const brands = Array.from(
      new Set(
        data.sku.filter((s) => !filters.category || s.category === filters.category).map((s) => s.brand),
      ),
    ).sort();
    const simple = (xs: string[]) => xs.map((x) => ({ value: x, label: x }));
    return {
      region: simple(data.region),
      channel: simple(data.channel),
      customer: customers.map((c) => ({ value: c.customer, label: c.customer })),
      category: simple(data.category),
      brand: simple(brands),
      sku: skus.map((s) => ({ value: s.sku, label: `${s.sku} · ${s.product}` })),
    } as Record<FilterDim, { value: string; label: string }[]>;
  }, [data, filters]);

  const n = activeFilterCount(filters);
  return (
    <div className="card mb-5 flex flex-wrap items-center gap-2 px-3 py-2.5">
      <span className="flex items-center gap-1.5 px-1 text-xs font-semibold text-muted">
        <SlidersHorizontal size={14} /> Filters
      </span>
      {dims.map((d) => (
        <select
          key={d}
          aria-label={LABELS[d]}
          value={filters[d] ?? ""}
          onChange={(e) => setFilter(d, e.target.value || undefined)}
          className={`input w-auto max-w-[220px] py-1.5 text-[13px] ${filters[d] ? "border-brand/50 bg-blue-50/50" : ""}`}
        >
          <option value="">All {PLURAL[d]}</option>
          {(options[d] ?? []).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ))}
      {n > 0 && (
        <button type="button" className="btn-ghost px-2 py-1.5 text-xs" onClick={clear}>
          <FilterX size={14} /> Clear ({n})
        </button>
      )}
      {showMeasure && (
        <div className="ml-auto">
          <Segmented<Measure>
            value={measure}
            onChange={setMeasure}
            options={[
              { value: "revenue", label: "Revenue (R$)" },
              { value: "units", label: "Units" },
            ]}
          />
        </div>
      )}
    </div>
  );
}
