/**
 * "Quais séries tratar primeiro?" (spec §2.3.4): the Cliente × SKU exceptions of the current cut,
 * ranked by the backend (impact × chance for fc_*, impact otherwise).
 *
 * Plano: "Perdas · Ganhos · Todas". Previsão: the chip "Causa: {label} ×" while a cause filters the
 * list. 15 rows, then "Ver mais" appends the next 15 (offset in local state: any change of the URL
 * or of the toggle starts again from the first 15). Each row has an "Ações" menu (Abrir ficha ·
 * Criar ajuste comercial · Simular cenário · Perguntar à IA); the series name opens the card.
 *
 * A plain table (not the sortable `DataTable`): the order is the backend's priority, and sorting
 * only the loaded page would misrepresent it.
 */
import { useQueries } from "@tanstack/react-query";
import clsx from "clsx";
import { ChevronDown, Ellipsis, X } from "lucide-react";
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { useGet } from "../../hooks/useApi";
import { LENS_OF, type Cmp } from "../../lib/deviationsUrl";
import { full, money, pct, type Measure } from "../../lib/format";
import { errorWord, probColor, varianceText } from "../../lib/ibcs";
import { api, type Params } from "../../services/api";
import type { ActionSpec, DeviationExceptions, ExceptionRow } from "../../types/deviations";
import { Card, ConfidenceBadge, ErrorState, Segmented } from "../ui";
import { ACTION_ICON } from "./actions";
import { Skeleton, TagChip, TagChips } from "./common";

export const EXCEPTIONS_QUESTION = "Quais séries tratar primeiro?";
export const EXCEPTIONS_PATH = "/api/deviations/exceptions";
export const PAGE_SIZE = 15;

export type Direction = "adverse" | "favorable" | "all";

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/* ------------------------------------------------------------- row actions menu */

const MENU_WIDTH = 236;

function RowActions({
  row,
  onRun,
}: {
  row: ExceptionRow;
  onRun: (a: ActionSpec, row: ExceptionRow) => void;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  const close = useCallback((focusButton = true) => {
    setOpen(false);
    setPos(null);
    if (focusButton) btnRef.current?.focus();
  }, []);

  // Position the menu next to the button, inside the viewport (flips up near the bottom edge).
  useLayoutEffect(() => {
    if (!open) return;
    const btn = btnRef.current?.getBoundingClientRect();
    const menu = menuRef.current;
    if (!btn || !menu) return;
    const h = menu.offsetHeight;
    const vw = window.innerWidth || document.documentElement.clientWidth;
    const vh = window.innerHeight || document.documentElement.clientHeight;
    const left = Math.max(8, Math.min(btn.right - MENU_WIDTH, vw - MENU_WIDTH - 8));
    const below = btn.bottom + 6;
    const top = below + h > vh - 8 && btn.top - h - 6 > 8 ? btn.top - h - 6 : below;
    setPos({ top, left });
    menu.querySelector<HTMLButtonElement>("[role='menuitem']")?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (menuRef.current?.contains(t) || btnRef.current?.contains(t)) return;
      close(false);
    };
    const onScroll = () => close(false);
    document.addEventListener("mousedown", onDown);
    window.addEventListener("resize", onScroll);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("resize", onScroll);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open, close]);

  const onMenuKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>("[role='menuitem']") ?? []);
    const i = items.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      items[(i + 1) % items.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      items[(i - 1 + items.length) % items.length]?.focus();
    } else if (e.key === "Tab") {
      close(false);
    }
  };

  if (!row.actions?.length) return <span className="text-muted">—</span>;
  return (
    <>
      <button
        ref={btnRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={`Ações para ${row.customer} · ${row.sku}`}
        onClick={() => (open ? close() : setOpen(true))}
        title="Ações"
        className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-line bg-white/90 text-ink-2 transition hover:bg-white hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        <Ellipsis size={16} aria-hidden />
      </button>
      {open &&
        createPortal(
          <div
            ref={menuRef}
            id={menuId}
            role="menu"
            aria-label={`Ações para ${row.customer} · ${row.sku}`}
            onKeyDown={onMenuKey}
            style={{
              position: "fixed",
              top: pos?.top ?? 0,
              left: pos?.left ?? 0,
              width: MENU_WIDTH,
              visibility: pos ? "visible" : "hidden",
            }}
            className="z-[55] flex flex-col rounded-2xl border border-line bg-white p-1.5 shadow-[0_18px_40px_-14px_rgba(45,50,119,0.35)]"
          >
            {row.actions.map((a, i) => {
              const Icon = ACTION_ICON[a.kind];
              return (
                <button
                  key={`${a.kind}-${i}`}
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    close(false);
                    onRun(a, row);
                  }}
                  className="flex items-center gap-2 rounded-xl px-3 py-2 text-left text-[13px] font-medium text-ink transition hover:bg-[#f4f7ff] focus-visible:bg-[#eaf2ff] focus-visible:outline-none"
                >
                  {Icon && <Icon size={15} aria-hidden className="shrink-0 text-ink-2" />}
                  {a.label}
                </button>
              );
            })}
          </div>,
          document.body,
        )}
    </>
  );
}

/* ------------------------------------------------------------------- table */

interface Col {
  label: string;
  align?: "right";
  minWidth?: number;
  cell: (r: ExceptionRow) => ReactNode;
}

function SeriesCell({ r, onOpen }: { r: ExceptionRow; onOpen: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(r.series_id)}
      className="block max-w-[320px] rounded-lg text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
    >
      <span className="block break-words text-[13px] font-semibold leading-snug text-ink hover:text-brand">
        {r.customer} · {r.sku}
      </span>
      <span className="block break-words text-[11.5px] leading-snug text-muted">{r.product}</span>
      {r.confidence && (
        <span className="mt-1 flex items-center gap-1.5 text-[11px] text-muted">
          Confiança <ConfidenceBadge value={r.confidence} />
        </span>
      )}
    </button>
  );
}

function planColumns(measure: Measure, withProb: boolean, onOpen: (id: string) => void): Col[] {
  return [
    { label: "Série", minWidth: 210, cell: (r) => <SeriesCell r={r} onOpen={onOpen} /> },
    {
      label: measure === "units" ? "Desvio (un.)" : "Desvio (R$)",
      align: "right",
      cell: (r) =>
        isNum(r.variance) ? (
          <span className="block leading-snug">
            <span className="font-semibold" style={{ color: r.variance < 0 ? "#b42323" : "#0b7a0b" }}>
              {varianceText(r.variance, measure)}
            </span>
            {isNum(r.variance_pct) && (
              <span className="block text-[11px] text-muted">{pct(r.variance_pct, 1, true)}</span>
            )}
          </span>
        ) : (
          "—"
        ),
    },
    ...(withProb
      ? [
          {
            label: "Chance",
            align: "right" as const,
            cell: (r: ExceptionRow) =>
              isNum(r.prob_hit) ? (
                <span className="inline-flex items-center justify-end gap-1.5">
                  <span
                    aria-hidden
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ background: probColor(r.prob_hit) }}
                  />
                  {pct(r.prob_hit, 0)}
                </span>
              ) : (
                "—"
              ),
          },
        ]
      : []),
    { label: "Causa", minWidth: 150, cell: (r) => <TagChips tags={r.tags} /> },
    {
      label: "Ação recomendada",
      minWidth: 200,
      cell: (r) => (
        <span className="block break-words leading-snug">{r.recommended_action?.label ?? "—"}</span>
      ),
    },
  ];
}

function forecastColumns(onOpen: (id: string) => void): Col[] {
  return [
    { label: "Série", minWidth: 210, cell: (r) => <SeriesCell r={r} onOpen={onOpen} /> },
    {
      label: "Erro (R$)",
      align: "right",
      cell: (r) => (
        <span className="block leading-snug">
          <span className="font-semibold">{money(r.abs_error)}</span>
          {isNum(r.wmape) && <span className="block text-[11px] text-muted">WMAPE {pct(r.wmape)}</span>}
        </span>
      ),
    },
    {
      label: "Viés",
      align: "right",
      cell: (r) =>
        isNum(r.bias) ? (
          <span className="block leading-snug">
            {pct(r.bias, 1, true)}
            <span className="block text-[11px] text-muted">
              {r.bias === 0 ? "sem viés" : errorWord(r.bias)}
            </span>
            {isNum(r.tracking_signal) && (
              <span className="block text-[11px] text-muted">
                sinal de rastreamento {r.tracking_signal > 0 ? "+" : ""}
                {full(r.tracking_signal, 1)}
              </span>
            )}
          </span>
        ) : (
          "—"
        ),
    },
    {
      label: "Causa principal",
      minWidth: 150,
      cell: (r) =>
        r.top_cause ? <TagChip>{r.top_cause.label}</TagChip> : <span className="text-muted">—</span>,
    },
    {
      label: "Ação recomendada",
      minWidth: 200,
      cell: (r) => (
        <span className="block break-words leading-snug">{r.recommended_action?.label ?? "—"}</span>
      ),
    },
  ];
}

const DIRECTION_EMPTY: Record<Direction, string> = {
  adverse: "Nenhuma série com perda acima dos limites de exceção neste recorte.",
  favorable: "Nenhuma série com ganho acima dos limites de exceção neste recorte.",
  all: "Nenhuma série acima dos limites de exceção neste recorte.",
};

export function ExceptionsTable({
  params,
  forecast,
  withProb,
  measure,
  causa,
  causaLabel,
  onClearCausa,
  onOpenSeries,
  onRun,
  enabled = true,
}: {
  /** `apiParams(state)` + focus_level/focus (+ cause in Previsão). */
  params: Params;
  forecast: boolean;
  /** fc_*: show "Chance de atingir". */
  withProb: boolean;
  measure: Measure;
  causa?: string;
  causaLabel?: string;
  onClearCausa: () => void;
  onOpenSeries: (seriesId: string) => void;
  onRun: (a: ActionSpec, row: ExceptionRow) => void;
  enabled?: boolean;
}) {
  const [direction, setDirection] = useState<Direction>("adverse");
  const query: Params = forecast ? { ...params } : { ...params, direction };
  const listKey = JSON.stringify(query);
  const [more, setMore] = useState<{ key: string; pages: number }>({ key: listKey, pages: 1 });
  const pages = more.key === listKey ? more.pages : 1;

  // Previous rows stay on screen while refetching, but only rows of the same lens and measure:
  // plan rows under the forecast columns (or R$ under "Desvio (un.)") would be wrong, not just old.
  const lensOf = (cmp: Params[string]) => LENS_OF[cmp as Cmp] ?? null;
  const sameShape = (prev?: Params) =>
    !!prev && lensOf(prev.cmp) === lensOf(query.cmp) && prev.measure === query.measure;
  const first = useGet<DeviationExceptions>(
    enabled ? EXCEPTIONS_PATH : null,
    { ...query, limit: PAGE_SIZE, offset: 0 },
    {
      placeholderData: (prev, prevQuery) =>
        sameShape(prevQuery?.queryKey?.[1] as Params | undefined) ? prev : undefined,
    },
  );
  const extra = useQueries({
    queries: Array.from({ length: Math.max(0, pages - 1) }, (_, i) => {
      const p: Params = { ...query, limit: PAGE_SIZE, offset: (i + 1) * PAGE_SIZE };
      return {
        queryKey: [EXCEPTIONS_PATH, p],
        queryFn: () => api.get<DeviationExceptions>(EXCEPTIONS_PATH, p),
        enabled,
      };
    }),
  });

  const total = first.data?.total ?? 0;
  const rows = [...(first.data?.rows ?? []), ...extra.flatMap((q) => q.data?.rows ?? [])];
  const loadingMore = extra.some((q) => q.isPending);
  const moreError = extra.find((q) => q.error)?.error ?? null;

  const columns = forecast ? forecastColumns(onOpenSeries) : planColumns(measure, withProb, onOpenSeries);
  // The chip names the cause even when the focused node no longer lists it among its causes: the
  // filtered rows all carry it as their top cause.
  const causeName = causaLabel ?? rows.find((r) => r.top_cause?.code === causa)?.top_cause?.label ?? causa;
  const refreshing = first.isPlaceholderData && first.isFetching;

  return (
    <Card
      data-visual="excecoes"
      data-question={EXCEPTIONS_QUESTION}
      title={EXCEPTIONS_QUESTION}
      subtitle={
        forecast
          ? "Séries com erro alto, viés persistente ou sinal de rastreamento fora do limite, ordenadas pelo erro em R$"
          : "Cliente × SKU com desvio relevante, ordenados pelo impacto em R$"
      }
      actions={
        forecast ? (
          causa ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-[#c9dcff] bg-[#eaf2ff] py-0.5 pl-3 pr-1 text-[12px] font-semibold text-[#1d3f8f]">
              Causa: {causeName}
              <button
                type="button"
                aria-label={`Remover filtro Causa: ${causeName}`}
                onClick={onClearCausa}
                className="flex h-6 w-6 items-center justify-center rounded-full transition hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                <X size={13} aria-hidden />
              </button>
            </span>
          ) : undefined
        ) : (
          <div role="group" aria-label="Mostrar séries com">
            <Segmented<Direction>
              size="xs"
              value={direction}
              options={[
                { value: "adverse", label: "Perdas" },
                { value: "favorable", label: "Ganhos" },
                { value: "all", label: "Todas" },
              ]}
              onChange={setDirection}
            />
          </div>
        )
      }
      className={clsx("transition-opacity", refreshing && "opacity-60")}
      aria-busy={refreshing || undefined}
    >
      {first.error && !first.data ? (
        <ErrorState error={first.error} />
      ) : !first.data ? (
        <Skeleton height={360} />
      ) : !rows.length ? (
        <p className="py-10 text-center text-sm text-muted">
          {forecast
            ? causa
              ? "Nenhuma série em exceção com esta causa principal neste recorte."
              : "Nenhuma série em exceção neste recorte."
            : DIRECTION_EMPTY[direction]}
        </p>
      ) : (
        <>
          <div className="overflow-x-auto rounded-2xl border border-line bg-white/70">
            <table className="table-base tabular">
              <caption className="sr-only">{EXCEPTIONS_QUESTION}</caption>
              <thead>
                <tr>
                  {columns.map((c) => (
                    <th
                      key={c.label}
                      scope="col"
                      className={clsx(c.align === "right" && "text-right")}
                      style={c.minWidth ? { minWidth: c.minWidth } : undefined}
                    >
                      {c.label}
                    </th>
                  ))}
                  <th scope="col" className="text-right">
                    Ações
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={`${r.series_id}-${i}`}>
                    {columns.map((c) => (
                      <td
                        key={c.label}
                        className={clsx(c.align === "right" ? "text-right" : "whitespace-normal")}
                        style={c.minWidth ? { minWidth: c.minWidth } : undefined}
                      >
                        {c.cell(r)}
                      </td>
                    ))}
                    <td className="text-right">
                      <RowActions row={r} onRun={onRun} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-[12px] text-muted">
            <span>
              Mostrando {rows.length.toLocaleString("pt-BR")} de {total.toLocaleString("pt-BR")}{" "}
              {total === 1 ? "série" : "séries"}
            </span>
            {rows.length < total && (
              <button
                type="button"
                className="btn-secondary px-3.5 py-1.5 text-[12.5px]"
                disabled={loadingMore}
                onClick={() => setMore({ key: listKey, pages: pages + 1 })}
              >
                <ChevronDown size={14} aria-hidden /> {loadingMore ? "Carregando…" : "Ver mais"}
              </button>
            )}
          </div>
          {moreError && (
            <div className="mt-2">
              <ErrorState error={moreError} />
            </div>
          )}
        </>
      )}
    </Card>
  );
}
