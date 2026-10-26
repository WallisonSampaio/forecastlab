/**
 * Feasibility range (report chapter "Meta", spec §2.2.2): the consensus P10–P90 band (FC hatch)
 * with the P50 point, the budget (PL: white with ink outline) and the target (TG: dashed tick).
 * Moved from pages/SOP.tsx (spec §5 F2); labels are nudged apart so they never overlap.
 */
import { useId } from "react";

import { ChartFrame } from "../components/ui";
import { IBCS, useElementWidth } from "../lib/ibcs";

export interface FeasibilityRangeProps {
  a: { p10: number; p50: number; p90: number; target: number; budget: number };
  f: (v: number) => string;
  /** Accessible name; a sentence with the five values is built when omitted. */
  ariaLabel?: string;
}

/**
 * Nudge label centres (in % of the width) apart so they never overlap, keeping their
 * order and staying inside [lo, hi].
 */
function spread(xs: number[], gap: number, lo: number, hi: number): number[] {
  const order = xs.map((x, i) => ({ x, i })).sort((p, q) => p.x - q.x);
  const pos = order.map((o) => Math.min(hi, Math.max(lo, o.x)));
  for (let i = 1; i < pos.length; i++) pos[i] = Math.max(pos[i], pos[i - 1] + gap);
  for (let i = pos.length - 1; i >= 0; i--) {
    const cap = i === pos.length - 1 ? hi : pos[i + 1] - gap;
    pos[i] = Math.min(pos[i], cap);
  }
  if (pos.length) pos[0] = Math.max(pos[0], lo);
  const out = new Array<number>(xs.length);
  order.forEach((o, k) => (out[o.i] = pos[k]));
  return out;
}

const LABEL_W = 96; // px reserved per label ("R$ 110,34 mi")
const TRACK_Y = 54;
const TRACK_H = 14;
const MID = TRACK_Y + TRACK_H / 2;

export function FeasibilityRange({ a, f, ariaLabel }: FeasibilityRangeProps) {
  const { ref, width } = useElementWidth<HTMLDivElement>();
  const hatchId = `fr-hatch-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const w = width || 420;
  const edge = (LABEL_W / 2 / w) * 100;
  const gap = (LABEL_W / w) * 100;
  // Without a budget (0) the marker would squash the scale towards zero, so it is left out.
  const hasBudget = Number.isFinite(a.budget) && a.budget > 0;
  const vals = [a.p10, a.p50, a.p90, a.target, ...(hasBudget ? [a.budget] : [])].filter((v) =>
    Number.isFinite(v),
  );
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const x = (v: number) => (max > min ? edge + ((v - min) / (max - min)) * (100 - 2 * edge) : 50);

  const top = [
    { key: "P10", v: a.p10 },
    { key: "P50", v: a.p50 },
    { key: "P90", v: a.p90 },
  ];
  const bottom = [...(hasBudget ? [{ key: "Orçamento", v: a.budget }] : []), { key: "Meta", v: a.target }];
  const topX = spread(
    top.map((m) => x(m.v)),
    gap,
    edge,
    100 - edge,
  );
  const botX = spread(
    bottom.map((m) => x(m.v)),
    gap,
    edge,
    100 - edge,
  );
  const p = (v: number) => `${v}%`;
  const label =
    ariaLabel ??
    `Faixa provável P10–P90 do consenso de ${f(a.p10)} a ${f(a.p90)}; P50 ${f(a.p50)};` +
      `${hasBudget ? ` orçamento ${f(a.budget)};` : ""} meta ${f(a.target)}`;

  return (
    <ChartFrame
      ariaLabel={label}
      columns={[{ label: "Marcador" }, { label: "Valor", align: "right" }]}
      rows={[
        { key: "p10", cells: ["P10 (consenso)", f(a.p10)] },
        { key: "p50", cells: ["P50 (consenso)", f(a.p50)] },
        { key: "p90", cells: ["P90 (consenso)", f(a.p90)] },
        ...(hasBudget ? [{ key: "budget", cells: ["Orçamento", f(a.budget)] }] : []),
        { key: "target", cells: ["Meta", f(a.target)] },
      ]}
      legend={
        <>
          <span className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="ibcs-hatch inline-block h-3 w-5 rounded-[3px] border border-[#1b1f3b]"
            />
            Faixa provável P10–P90 (consenso)
          </span>
          {hasBudget && (
            <span className="inline-flex items-center gap-1.5">
              <span
                aria-hidden
                className="inline-block h-3 w-3 rounded-full border-[1.5px] border-[#1b1f3b] bg-white"
              />
              Orçamento
            </span>
          )}
          <span className="inline-flex items-center gap-1.5">
            <svg aria-hidden width="6" height="14" className="shrink-0">
              <line x1="3" x2="3" y1="0" y2="14" stroke={IBCS.ink} strokeWidth={2} strokeDasharray="3 2.5" />
            </svg>
            Meta
          </span>
        </>
      }
    >
      <div ref={ref} className="w-full">
        <svg width="100%" height={128} role="img" aria-label={label} className="block overflow-visible">
          <defs>
            <pattern
              id={hatchId}
              width="5"
              height="5"
              patternUnits="userSpaceOnUse"
              patternTransform="rotate(45)"
            >
              <rect width="5" height="5" fill="#fff" />
              <rect width="1.5" height="5" fill={IBCS.ink} fillOpacity={0.55} />
            </pattern>
          </defs>

          {/* track + probable band (FC hatch) */}
          <rect x="0" y={TRACK_Y} width="100%" height={TRACK_H} rx={TRACK_H / 2} fill="#eef1fa" />
          <rect
            x={p(x(a.p10))}
            y={TRACK_Y}
            width={p(Math.max(0, x(a.p90) - x(a.p10)))}
            height={TRACK_H}
            rx={3}
            fill={`url(#${hatchId})`}
            stroke={IBCS.ink}
            strokeWidth={IBCS.border}
          />

          {/* connectors */}
          {top.map((m, i) => (
            <line
              key={`ct-${m.key}`}
              x1={p(x(m.v))}
              y1={TRACK_Y - 3}
              x2={p(topX[i])}
              y2={34}
              stroke={IBCS.ink}
              strokeOpacity={0.35}
              strokeWidth={1}
            />
          ))}
          {bottom.map((m, i) => (
            <line
              key={`cb-${m.key}`}
              x1={p(x(m.v))}
              y1={TRACK_Y + TRACK_H + 9}
              x2={p(botX[i])}
              y2={90}
              stroke={IBCS.ink}
              strokeOpacity={0.35}
              strokeWidth={1}
            />
          ))}

          {/* P50 (consensus) */}
          <circle cx={p(x(a.p50))} cy={MID} r={6.5} fill={IBCS.ink} stroke="#fff" strokeWidth={2.5} />
          {/* budget: PL outline */}
          {hasBudget && (
            <circle
              cx={p(x(a.budget))}
              cy={MID}
              r={6}
              fill="#fff"
              stroke={IBCS.ink}
              strokeWidth={IBCS.border + 0.5}
            />
          )}
          {/* target: TG dashed tick */}
          <line
            x1={p(x(a.target))}
            x2={p(x(a.target))}
            y1={TRACK_Y - 9}
            y2={TRACK_Y + TRACK_H + 9}
            stroke={IBCS.ink}
            strokeWidth={2}
            strokeDasharray="3 2.5"
          />

          {/* labels */}
          {top.map((m, i) => (
            <g key={`lt-${m.key}`}>
              <text x={p(topX[i])} y={12} textAnchor="middle" fontSize={11} fontWeight={700} fill={IBCS.ink2}>
                {m.key}
              </text>
              <text
                x={p(topX[i])}
                y={27}
                textAnchor="middle"
                fontSize={11.5}
                fontWeight={600}
                fill={IBCS.ink}
                className="tabular"
              >
                {f(m.v)}
              </text>
            </g>
          ))}
          {bottom.map((m, i) => (
            <g key={`lb-${m.key}`}>
              <text
                x={p(botX[i])}
                y={104}
                textAnchor="middle"
                fontSize={11}
                fontWeight={700}
                fill={IBCS.ink2}
              >
                {m.key}
              </text>
              <text
                x={p(botX[i])}
                y={119}
                textAnchor="middle"
                fontSize={11.5}
                fontWeight={600}
                fill={IBCS.ink}
                className="tabular"
              >
                {f(m.v)}
              </text>
            </g>
          ))}
        </svg>
      </div>
    </ChartFrame>
  );
}
