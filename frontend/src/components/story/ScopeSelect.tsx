import clsx from "clsx";
import { X } from "lucide-react";

import { REPORT_SCOPE_DIMS, type ReportScope, type ReportScopeDim } from "../../lib/routes";
import { useDimensions } from "../FilterBar";
import { SCOPE_DIM_LABEL, scopeEntry } from "./helpers";

// Option value: "region=Sul" (dimension keys never contain "=", members may).
const encode = (dim: ReportScopeDim, member: string) => `${dim}=${member}`;
function decode(value: string): ReportScope {
  const i = value.indexOf("=");
  if (i < 0) return {};
  const dim = value.slice(0, i) as ReportScopeDim;
  const member = value.slice(i + 1);
  return REPORT_SCOPE_DIMS.includes(dim) && member ? { [dim]: member } : {};
}

/**
 * "Escopo" selector of the report (spec §1.4, §2.2.1): "Empresa toda" plus optgroups Região / Canal /
 * Categoria from `useDimensions()`. One dimension, one member, or none. The page writes the choice to
 * the URL, mirrors it to `useFilters` and saves it for the session.
 */
export function ScopeSelect({
  value,
  onChange,
}: {
  value: ReportScope;
  onChange: (scope: ReportScope) => void;
}) {
  const { data: dims } = useDimensions();
  const current = scopeEntry(value);
  const selected = current ? encode(current.dim, current.member) : "";
  // While the dimensions load (or if the member left the base), the current scope still shows.
  const known = !!current && !!dims?.[current.dim]?.includes(current.member);
  return (
    <label className="inline-flex items-center gap-2">
      <span className="text-[12px] font-semibold text-ink-2">Escopo</span>
      <select
        aria-label="Escopo do relatório"
        className={clsx(
          "input w-auto min-w-[180px] max-w-[280px] py-2 text-[13px] font-medium",
          current && "border-brand/40 bg-[#eef4ff] text-[#2364d2]",
        )}
        value={selected}
        onChange={(e) => onChange(decode(e.target.value))}
      >
        <option value="">Empresa toda</option>
        {current && !known && (
          <option value={selected}>{`${SCOPE_DIM_LABEL[current.dim]}: ${current.member}`}</option>
        )}
        {REPORT_SCOPE_DIMS.map((dim) =>
          dims?.[dim]?.length ? (
            <optgroup key={dim} label={SCOPE_DIM_LABEL[dim]}>
              {dims[dim].map((m) => (
                <option key={m} value={encode(dim, m)}>
                  {m}
                </option>
              ))}
            </optgroup>
          ) : null,
        )}
      </select>
    </label>
  );
}

/**
 * Scope chip, always visible (spec §1.4): "Escopo: Sul ×", where × clears the scope; "Escopo: Empresa
 * toda" without a button when there is none.
 */
export function ScopeChip({ value, onClear }: { value: ReportScope; onClear?: () => void }) {
  const current = scopeEntry(value);
  return (
    <span
      data-scope-chip
      className="inline-flex items-center gap-1 rounded-full border border-line bg-white/90 py-1 pl-3 pr-1 text-[12px] font-semibold text-ink-2 shadow-[0_2px_8px_-5px_rgba(45,50,119,0.3)]"
    >
      <span className="break-words">
        Escopo: <span className="text-ink">{current?.member ?? "Empresa toda"}</span>
      </span>
      {current && onClear ? (
        <button
          type="button"
          onClick={onClear}
          aria-label={`Remover escopo ${current.member}`}
          className="ml-0.5 flex h-5 w-5 items-center justify-center rounded-full text-muted transition hover:bg-[#eef1fa] hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/60"
        >
          <X size={12} aria-hidden />
        </button>
      ) : (
        <span className="w-2" aria-hidden />
      )}
    </span>
  );
}

export default ScopeSelect;
