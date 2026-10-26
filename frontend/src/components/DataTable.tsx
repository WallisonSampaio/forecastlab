import clsx from "clsx";
import { ArrowDown, ArrowUp, Search } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { formatValue } from "../lib/format";

export interface Column<T> {
  key: string;
  label: string;
  format?: string;
  align?: "left" | "right" | "center";
  render?: (row: T) => ReactNode;
  sortValue?: (row: T) => number | string | null | undefined;
  width?: number;
  /** Free-text column: cells wrap (`break-words`) instead of staying on one line. */
  wrap?: boolean;
  /** Minimum width in px (useful with `wrap`). */
  minWidth?: number;
}

interface Props<T> {
  rows: T[];
  columns: Column<T>[];
  maxHeight?: number;
  searchable?: boolean;
  searchKeys?: string[];
  onRowClick?: (row: T) => void;
  rowKey?: (row: T, i: number) => string;
  initialSort?: { key: string; dir: "asc" | "desc" };
  empty?: ReactNode;
  dense?: boolean;
  activeKey?: string;
}

export function DataTable<T extends Record<string, any>>({
  rows,
  columns,
  maxHeight = 480,
  searchable,
  searchKeys,
  onRowClick,
  rowKey,
  initialSort,
  empty,
  dense,
  activeKey,
}: Props<T>) {
  const [sort, setSort] = useState(initialSort);
  const [q, setQ] = useState("");
  const toggleSort = (key: string) =>
    setSort((s) => (s?.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" }));
  const view = useMemo(() => {
    let out = rows;
    if (q) {
      const needle = q.toLowerCase();
      const keys = searchKeys ?? columns.map((c) => c.key);
      out = out.filter((r) =>
        keys.some((k) =>
          String(r[k] ?? "")
            .toLowerCase()
            .includes(needle),
        ),
      );
    }
    if (sort) {
      const col = columns.find((c) => c.key === sort.key);
      const get = col?.sortValue ?? ((r: T) => r[sort.key]);
      out = [...out].sort((a, b) => {
        const va = get(a);
        const vb = get(b);
        if (va == null && vb == null) return 0;
        if (va == null) return 1;
        if (vb == null) return -1;
        const cmp =
          typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb));
        return sort.dir === "asc" ? cmp : -cmp;
      });
    }
    return out;
  }, [rows, q, sort, columns, searchKeys]);

  return (
    <div>
      {searchable && (
        <div className="relative mb-3 max-w-sm">
          <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
          <input
            className="input pl-9"
            placeholder="Buscar…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      )}
      <div className="overflow-auto rounded-2xl border border-line bg-white/70" style={{ maxHeight }}>
        <table className={clsx("table-base tabular", dense && "[&_td]:py-1.5 [&_th]:py-2")}>
          <thead>
            <tr>
              {columns.map((c) => (
                <th
                  key={c.key}
                  scope="col"
                  tabIndex={0}
                  aria-sort={
                    sort?.key === c.key ? (sort.dir === "asc" ? "ascending" : "descending") : undefined
                  }
                  style={{ width: c.width, minWidth: c.minWidth }}
                  className={clsx(
                    "cursor-pointer select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand",
                    c.align === "right" && "text-right",
                    c.align === "center" && "text-center",
                  )}
                  onClick={() => toggleSort(c.key)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      toggleSort(c.key);
                    }
                  }}
                >
                  <span className="inline-flex items-center gap-1">
                    {c.label}
                    {sort?.key === c.key &&
                      (sort.dir === "asc" ? <ArrowUp size={11} /> : <ArrowDown size={11} />)}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {view.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="py-8 text-center text-muted">
                  {empty ?? "Nenhuma linha"}
                </td>
              </tr>
            )}
            {view.map((r, i) => {
              const key = rowKey ? rowKey(r, i) : String(i);
              return (
                <tr
                  key={key}
                  onClick={onRowClick ? () => onRowClick(r) : undefined}
                  className={clsx(onRowClick && "cursor-pointer", activeKey === key && "[&>td]:bg-[#eaf2ff]")}
                >
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      style={c.minWidth ? { minWidth: c.minWidth } : undefined}
                      className={clsx(
                        c.align === "right" && "text-right",
                        c.align === "center" && "text-center",
                        c.wrap && "whitespace-normal break-words",
                      )}
                    >
                      {c.render ? c.render(r) : formatValue(r[c.key], c.format)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-1.5 text-right text-[11px] text-muted">
        {view.length.toLocaleString("pt-BR")} {view.length === 1 ? "linha" : "linhas"}
      </div>
    </div>
  );
}
