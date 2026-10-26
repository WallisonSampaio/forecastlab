import clsx from "clsx";
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
  region: "Região",
  channel: "Canal",
  customer: "Cliente",
  category: "Categoria",
  brand: "Marca",
  sku: "SKU",
};

const ALL: Record<FilterDim, string> = {
  region: "Todas as regiões",
  channel: "Todos os canais",
  customer: "Todos os clientes",
  category: "Todas as categorias",
  brand: "Todas as marcas",
  sku: "Todos os SKUs",
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
    <div className="card mb-6 flex flex-wrap items-center gap-2 px-4 py-3">
      <span className="flex items-center gap-2 pr-1 text-xs font-bold uppercase tracking-wider text-muted">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#eaf2ff] text-brand">
          <SlidersHorizontal size={14} />
        </span>
        Filtros
      </span>
      {dims.map((d) => (
        <select
          key={d}
          aria-label={LABELS[d]}
          value={filters[d] ?? ""}
          onChange={(e) => setFilter(d, e.target.value || undefined)}
          className={clsx(
            "input w-auto max-w-[230px] py-2 text-[13px] font-medium",
            filters[d] && "border-brand/40 bg-[#eef4ff] text-[#2364d2]",
          )}
        >
          <option value="">{ALL[d]}</option>
          {(options[d] ?? []).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      ))}
      {n > 0 && (
        <button type="button" className="btn-ghost px-2.5 py-2 text-xs" onClick={clear}>
          <FilterX size={14} /> Limpar ({n})
        </button>
      )}
      {showMeasure && (
        <div className="ml-auto">
          <Segmented<Measure>
            value={measure}
            onChange={setMeasure}
            options={[
              { value: "revenue", label: "Receita (R$)" },
              { value: "units", label: "Unidades" },
            ]}
          />
        </div>
      )}
    </div>
  );
}
