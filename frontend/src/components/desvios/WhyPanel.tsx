/**
 * "Por que desviou?" (spec §2.3.4).
 * Plano: price / volume / mix / events bridge (`BridgeChart`) of the node or the focused member.
 * Previsão: root causes of the error (`CauseBars`, a click filters the exceptions table), the
 * systematic-vs-noise split and the champion models that carry the error.
 * Both: the "Diagnóstico" (2–3 backend sentences) and the action chips.
 */
import { Stethoscope } from "lucide-react";

import { BridgeChart } from "../../charts/BridgeChart";
import { CauseBars } from "../../charts/CauseBars";
import { money, pct } from "../../lib/format";
import { LENS_OF } from "../../lib/deviationsUrl";
import type { ActionSpec } from "../../types/deviations";
import { Card, ErrorState } from "../ui";
import { ActionButtons, Skeleton } from "./common";
import { SIDES, type DeviationNav, type FocusPayload } from "./state";

export const WHY_QUESTION = "Por que desviou?";

function Diagnosis({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <h4 className="label-xs mb-2 flex items-center gap-1.5">
        <Stethoscope size={13} aria-hidden /> Diagnóstico
      </h4>
      <ul className="flex flex-col gap-2">
        {items.map((s, i) => (
          <li key={i} className="flex gap-2.5 text-[13px] leading-relaxed text-ink">
            <span
              aria-hidden
              className="mt-[7px] inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-[#3483fa]"
            />
            <span className="min-w-0 break-words">{s}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function WhyPanel({
  nav,
  focus,
  error,
  onRun,
  className,
}: {
  nav: DeviationNav;
  /** Focus of the current comparison (undefined while loading). */
  focus?: FocusPayload;
  error: Error | null;
  onRun: (a: ActionSpec) => void;
  className?: string;
}) {
  const { state } = nav;
  const forecast = LENS_OF[state.cmp] === "previsao";
  const sides = SIDES[state.cmp];
  const who = focus?.focus?.label;
  const subtitle = forecast
    ? `Causas do erro${who ? ` · ${who}` : ""}`
    : `Ponte ${sides.reference} → ${sides.compared}${who ? ` · ${who}` : ""}`;

  let body;
  if (error && !focus) body = <ErrorState error={error} />;
  else if (!focus) body = <Skeleton height={420} />;
  else if (focus.available === false)
    body = (
      <p className="py-10 text-center text-sm text-muted">{focus.reason ?? "Sem dados para este recorte."}</p>
    );
  else
    body = (
      <div className="flex flex-col gap-5">
        {forecast ? (
          <div className="flex flex-col gap-3">
            {focus.causes?.length ? (
              <CauseBars
                causes={focus.causes}
                selected={state.causa}
                onSelect={(code) => nav.toggleCausa(code)}
                ariaLabel="Erro de previsão por causa"
              />
            ) : (
              <p className="text-sm text-muted">Sem causas calculadas para este recorte.</p>
            )}
            {(!!focus.split || !!focus.by_model?.length) && (
              <div className="flex flex-col gap-1 rounded-2xl bg-[#f6f8fe] px-4 py-3 text-[12.5px] leading-relaxed text-ink-2">
                {focus.split && (
                  <p>
                    <span className="font-semibold text-ink">Sistemático</span>{" "}
                    {money(focus.split.systematic)} ({pct(focus.split.systematic_share, 0)}) ·{" "}
                    <span className="font-semibold text-ink">Ruído que se compensa</span>{" "}
                    {money(focus.split.noise)}
                  </p>
                )}
                {!!focus.by_model?.length && (
                  <p>
                    <span className="font-semibold text-ink">Por modelo campeão:</span>{" "}
                    {focus.by_model
                      .slice(0, 3)
                      .map((m) => `${m.label} ${pct(m.share, 0)}`)
                      .join(" · ")}
                  </p>
                )}
              </div>
            )}
          </div>
        ) : focus.bridge?.length ? (
          <BridgeChart
            steps={focus.bridge}
            measure={state.medida}
            height={300}
            note={focus.bridge_note ?? undefined}
            ariaLabel={`Ponte de ${sides.reference.toLowerCase()} a ${sides.compared.toLowerCase()}: volume, mix, preço e eventos`}
          />
        ) : (
          <p className="text-sm text-muted">Sem ponte para este recorte.</p>
        )}
        <Diagnosis items={focus.diagnosis ?? []} />
        {!!focus.actions?.length && (
          <div>
            <h4 className="label-xs mb-2">O que fazer agora</h4>
            <ActionButtons actions={focus.actions} onRun={onRun} />
          </div>
        )}
      </div>
    );

  return (
    <Card
      data-visual="porque"
      data-question={WHY_QUESTION}
      title={WHY_QUESTION}
      subtitle={subtitle}
      className={className}
    >
      {body}
    </Card>
  );
}
