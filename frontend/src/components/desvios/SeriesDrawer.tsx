/**
 * "Ficha da série" (spec §2.3.6): right sheet opened by the URL key `serie`.
 *
 *   1. header: Cliente · SKU produto, chips (padrão, confiança, campeão/desafiante) and three mini
 *      values (reference, compared, Δ); fc_* adds "Últimos 12 meses: {x} vs orçamento"
 *   2. compact timeline (24 months of history + the horizon)
 *   3. "Evidências": backtest months with cause and evidence (Previsão) or the monthly plan
 *      comparison plus the series' bridge in words (Plano)
 *   4. "Ação recomendada"
 *   5. sticky action bar (Abrir no workspace · Criar ajuste comercial · Simular cenário · Perguntar à IA)
 */
import clsx from "clsx";
import { Lightbulb } from "lucide-react";
import type { ReactNode } from "react";

import { TimelineChart } from "../../charts/TimelineChart";
import { Drawer } from "../Drawer";
import { useGet } from "../../hooks/useApi";
import { apiParams, LENS_OF } from "../../lib/deviationsUrl";
import {
  fmtMeasure,
  money,
  monthLabel,
  pct,
  signedMeasure,
  signedMoney,
  type Measure,
} from "../../lib/format";
import { errorWord } from "../../lib/ibcs";
import { t } from "../../lib/labels";
import type { ActionSpec, EvidenceRow, MonthlyPlanRow } from "../../types/deviations";
import { ConfidenceBadge, ErrorState } from "../ui";
import { ActionButtons, Skeleton, TagChip } from "./common";
import { SIDES, isMonthCode, type DeviationNav, type SeriesPayload } from "./state";

export const SERIES_PATH = "/api/deviations/series";

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

function Mini({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="min-w-0 rounded-2xl bg-[#f6f8fe] px-3.5 py-2.5">
      <div className="text-[11.5px] font-medium leading-snug text-ink-2">{label}</div>
      <div className="mt-0.5 whitespace-nowrap text-[17px] font-bold leading-tight text-ink tabular">
        {value}
      </div>
      {sub && <div className="mt-0.5 text-[11px] leading-snug text-muted">{sub}</div>}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="label-xs">{title}</h3>
      {children}
    </section>
  );
}

function ForecastEvidence({ rows, month }: { rows: EvidenceRow[]; month?: string }) {
  if (!rows.length) return <p className="text-sm text-muted">Sem meses de backtest para esta série.</p>;
  return (
    <div className="overflow-x-auto rounded-2xl border border-line bg-white/70">
      <table className="table-base tabular text-[12.5px]">
        <caption className="sr-only">Evidências por mês de backtest</caption>
        <thead>
          <tr>
            <th scope="col">Mês</th>
            <th scope="col" className="text-right">
              Real
            </th>
            <th scope="col" className="text-right">
              Previsto
            </th>
            <th scope="col" className="text-right">
              Erro %
            </th>
            <th scope="col">Causa</th>
            <th scope="col" style={{ minWidth: 200 }}>
              Evidência
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={`${r.date}-${r.horizon_step}`}
              className={clsx(month && r.date.startsWith(month) && "[&>td]:bg-[#eaf2ff]")}
            >
              <td>{monthLabel(r.date)}</td>
              <td className="text-right">{money(r.actual)}</td>
              <td className="text-right">{money(r.forecast)}</td>
              <td className="text-right">
                {isNum(r.error_pct) ? (
                  <span className="block leading-snug">
                    {pct(r.error_pct, 1, true)}
                    <span className="block text-[10.5px] text-muted">{errorWord(r.error_pct)}</span>
                  </span>
                ) : (
                  "—"
                )}
              </td>
              <td className="whitespace-normal" style={{ minWidth: 130 }}>
                <TagChip tone={r.cause?.group === "controllable" ? "brand" : "neutral"}>
                  {r.cause?.label ?? "—"}
                </TagChip>
              </td>
              <td className="whitespace-normal break-words leading-snug" style={{ minWidth: 200 }}>
                {r.evidence}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PlanEvidence({
  rows,
  measure,
  reference,
  compared,
  month,
}: {
  rows: MonthlyPlanRow[];
  measure: Measure;
  reference: string;
  compared: string;
  month?: string;
}) {
  if (!rows.length) return <p className="text-sm text-muted">Sem meses com orçamento neste período.</p>;
  return (
    <div className="overflow-x-auto rounded-2xl border border-line bg-white/70">
      <table className="table-base tabular text-[12.5px]">
        <caption className="sr-only">Comparação mês a mês</caption>
        <thead>
          <tr>
            <th scope="col">Mês</th>
            <th scope="col" className="text-right">
              {reference}
            </th>
            <th scope="col" className="text-right">
              {compared}
            </th>
            <th scope="col" className="text-right">
              Δ
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.date} className={clsx(month && r.date.startsWith(month) && "[&>td]:bg-[#eaf2ff]")}>
              <td>{monthLabel(r.date)}</td>
              <td className="text-right">{fmtMeasure(r.p, measure)}</td>
              <td className="text-right">{fmtMeasure(r.x, measure)}</td>
              <td className="text-right">
                {isNum(r.variance) ? (
                  <span className="block leading-snug">
                    <span style={{ color: r.variance < 0 ? "#b42323" : "#0b7a0b" }} className="font-semibold">
                      {signedMeasure(r.variance, measure)}
                    </span>
                    <span className="block text-[10.5px] text-muted">
                      {isNum(r.variance_pct) ? pct(r.variance_pct, 1, true) : "—"}{" "}
                      {r.variance < 0 ? "abaixo" : "acima"}
                    </span>
                  </span>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** "Volume -R$ 70,1 mil · Mix -R$ 235,1 mil · Preço -R$ 11,2 mil · Eventos -R$ 1,4 mil" */
function bridgeText(effects: SeriesPayload["effects"], measure: Measure): string | null {
  if (!effects) return null;
  const parts: [string, number | null | undefined][] = [
    ["Volume", effects.volume],
    ["Mix", effects.mix],
    ["Preço", effects.price],
    ["Eventos", effects.events],
  ];
  const shown = parts
    .filter(([, v]) => isNum(v))
    .map(([k, v]) => `${k} ${signedMeasure(v as number, measure)}`);
  return shown.length ? shown.join(" · ") : null;
}

export function SeriesDrawer({
  nav,
  onRun,
  enabled = true,
}: {
  nav: DeviationNav;
  onRun: (a: ActionSpec) => void;
  /** False until the journey is ready (the endpoint needs a completed run). */
  enabled?: boolean;
}) {
  const { state } = nav;
  const serie = state.serie;
  const forecast = LENS_OF[state.cmp] === "previsao";
  const api = apiParams(state);
  const measure: Measure = forecast ? "revenue" : state.medida;
  const { data, error, isFetching, isPlaceholderData } = useGet<SeriesPayload>(
    serie && enabled ? SERIES_PATH : null,
    { series_id: serie, cmp: state.cmp, period: api.period as string, measure },
  );
  // placeholderData would show the previous series/comparison (another shape): skeleton instead.
  const d = data && !isPlaceholderData && data.series_id === serie ? data : undefined;
  const sides = SIDES[state.cmp];
  const month = isMonthCode(state.periodo) ? state.periodo : undefined;
  const title = d?.label ?? (serie ? serie.replace("|", " · ") : "Ficha da série");

  const rv = d?.summary?.realized_variance_pct;
  const showRecurrence = !forecast && state.cmp !== "ac_pl" && isNum(rv);
  const lastActual = d?.timeline?.filter((r) => r.actual != null).at(-1)?.date;
  const fmt = (v: number | null | undefined) => (forecast ? money(v) : fmtMeasure(v, measure));

  let body: ReactNode;
  if (error && !d) body = <ErrorState error={error} />;
  else if (!d)
    body = (
      <div className="flex flex-col gap-4" aria-busy={isFetching || undefined}>
        <Skeleton height={72} />
        <Skeleton height={200} />
        <Skeleton height={220} />
      </div>
    );
  else
    body = (
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-1.5">
            {d.header.series_type_label && <TagChip>Padrão: {d.header.series_type_label}</TagChip>}
            {d.header.confidence && (
              <span className="inline-flex items-center gap-1 text-[11.5px] font-medium text-ink-2">
                Confiança <ConfidenceBadge value={d.header.confidence} />
              </span>
            )}
            {d.header.champion && (
              <TagChip>
                Campeão: {t.model(d.header.champion)}
                {d.header.challenger ? ` · desafiante: ${t.model(d.header.challenger)}` : ""}
              </TagChip>
            )}
          </div>
          {d.available === false ? (
            <p className="text-sm text-muted">{d.reason ?? "Sem dados desta série para a comparação."}</p>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              <Mini label={sides.reference} value={fmt(d.summary.reference)} />
              <Mini label={sides.compared} value={fmt(d.summary.compared)} />
              <Mini
                label={forecast ? "Erro líquido" : sides.delta}
                value={
                  <span
                    style={
                      isNum(d.summary.variance) && !forecast
                        ? { color: d.summary.variance < 0 ? "#b42323" : "#0b7a0b" }
                        : undefined
                    }
                  >
                    {forecast ? signedMoney(d.summary.variance) : signedMeasure(d.summary.variance, measure)}
                  </span>
                }
                sub={
                  isNum(d.summary.variance_pct)
                    ? forecast
                      ? `viés ${pct(d.summary.variance_pct, 1, true)} · ${errorWord(d.summary.variance_pct)}`
                      : `${pct(d.summary.variance_pct, 1, true)} ${(d.summary.variance ?? 0) < 0 ? "abaixo" : "acima"}`
                    : undefined
                }
              />
            </div>
          )}
          {showRecurrence && (
            <p className="text-[12px] text-muted">Últimos 12 meses: {pct(rv, 1, true)} vs orçamento</p>
          )}
        </div>

        {!!d.timeline?.length && (
          <TimelineChart
            rows={d.timeline}
            measure={measure}
            lastActual={lastActual}
            height={200}
            show={["actual", "base", "consensus", "budget", "backtest", "band"]}
            hidden={[]}
          />
        )}

        <Section title="Evidências">
          {forecast ? (
            <ForecastEvidence rows={d.evidence ?? []} month={month} />
          ) : (
            <>
              <PlanEvidence
                rows={d.months ?? []}
                measure={measure}
                reference={sides.reference}
                compared={sides.compared}
                month={month}
              />
              {bridgeText(d.effects, measure) && (
                <p className="text-[12px] leading-relaxed text-ink-2">
                  <span className="font-semibold text-ink">Ponte da série:</span>{" "}
                  {bridgeText(d.effects, measure)}
                </p>
              )}
            </>
          )}
        </Section>

        <Section title="Ação recomendada">
          <p className="flex gap-2 text-[13.5px] leading-relaxed text-ink">
            <Lightbulb size={16} aria-hidden className="mt-0.5 shrink-0 text-[#c98a00]" />
            <span className="min-w-0 break-words">
              {d.recommended_action?.label ?? "Monitorar no próximo ciclo."}
            </span>
          </p>
          {!!d.future_overrides?.length && (
            <p className="text-[12px] leading-relaxed text-muted">
              Ajustes já cadastrados no horizonte:{" "}
              {d.future_overrides
                .map((o) => `${o.event_type} em ${monthLabel(o.date)} (${pct(o.uplift_pct, 0, true)})`)
                .join(" · ")}
            </p>
          )}
        </Section>
      </div>
    );

  return (
    <Drawer
      open={!!serie}
      title={title}
      subtitle={d ? `${d.header.region} · ${d.header.channel} · ${d.header.category}` : undefined}
      onClose={nav.closeSerie}
      footer={
        d?.actions?.length ? <ActionButtons actions={d.actions} onRun={onRun} variant="bar" /> : undefined
      }
    >
      {body}
    </Drawer>
  );
}
