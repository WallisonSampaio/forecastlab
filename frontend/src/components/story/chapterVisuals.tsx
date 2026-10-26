/**
 * The one visual of each report chapter (spec §2.2.2): a switch on `visual.kind`. Every block carries
 * `data-visual` + `data-question` (spec §2.0, rule 1); the chart frames bring their own "Ver tabela".
 */
import type { ReactNode } from "react";

import { BridgeChart } from "../../charts/BridgeChart";
import { CauseBars } from "../../charts/CauseBars";
import { FeasibilityRange } from "../../charts/FeasibilityRange";
import { VarianceBars } from "../../charts/VarianceBars";
import { VarianceColumns } from "../../charts/VarianceColumns";
import { formatKpi, money, pct } from "../../lib/format";
import type { Chapter } from "../../types/story";
import { Card, ClassBadge, KpiCard } from "../ui";
import { DecisionTable } from "./DecisionTable";
import { visualData, visualTitle } from "./helpers";

/** Most KPI cards in the Resumo row (spec §2.0, rule 2). */
const MAX_KPIS = 4;

export interface ChapterVisualProps {
  chapter: Chapter;
  horizonMonths: number;
  /** variance_bars: a click on a member opens it in the deep dive. */
  onOpenMember?: (level: string, member: string) => void;
}

/** The chapter's visual block (exactly one per chapter). */
export function ChapterVisual({ chapter, horizonMonths, onOpenMember }: ChapterVisualProps) {
  const kind = chapter.visual.kind;
  const question = chapter.question;
  const title = visualTitle(chapter);

  const block = (body: ReactNode, subtitle?: ReactNode) => (
    <Card data-visual={kind} data-question={question} title={title} subtitle={subtitle} className="h-full">
      {body}
    </Card>
  );

  switch (kind) {
    case "kpis": {
      const cards = (visualData<"kpis">(chapter).cards ?? []).slice(0, MAX_KPIS);
      // A row of KPI tiles, not a card around cards: each tile is already a card.
      return (
        <section data-visual="kpis" data-question={question} aria-label={title}>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {cards.map((c) => (
              <KpiCard
                key={c.id}
                label={c.label}
                value={formatKpi(c)}
                delta={c.delta ?? undefined}
                deltaTone={c.delta_tone ?? "neutral"}
                hint={c.hint ?? undefined}
              />
            ))}
          </div>
        </section>
      );
    }
    case "bridge": {
      const d = visualData<"bridge">(chapter);
      return block(<BridgeChart steps={d.steps ?? []} measure="revenue" ariaLabel={title} note={d.note} />);
    }
    case "cause_bars": {
      const d = visualData<"cause_bars">(chapter);
      return block(
        <CauseBars causes={d.causes ?? []} ariaLabel={title} note={d.note} />,
        Number.isFinite(d.total_abs_error)
          ? `${money(d.total_abs_error)} de erro absoluto fora da amostra, repartido por causa.`
          : undefined,
      );
    }
    case "monthly_variance": {
      const d = visualData<"monthly_variance">(chapter);
      return block(
        <VarianceColumns
          rows={d.rows ?? []}
          mode="plan"
          xKind="FC"
          xLabel={d.x_label || "Consenso"}
          pLabel={d.p_label || "Orçamento"}
          measure="revenue"
          quarters={d.quarters}
          ariaLabel={title}
        />,
      );
    }
    case "variance_bars": {
      const d = visualData<"variance_bars">(chapter);
      const level = d.level || "customer";
      // Gender-neutral copy: the level may be "cliente", "categoria" or "SKU".
      return block(
        <VarianceBars
          rows={d.rows ?? []}
          mode="plan"
          measure="revenue"
          others={d.others}
          onSelect={onOpenMember ? (key) => onOpenMember(level, key) : undefined}
          ariaLabel={title}
        />,
        onOpenMember
          ? "Perdas primeiro, depois ganhos. Clique em uma linha para abri-la no deep dive."
          : undefined,
      );
    }
    case "feasibility_range": {
      const d = visualData<"feasibility_range">(chapter);
      return block(
        <>
          <div className="mb-5 flex flex-wrap items-end gap-x-5 gap-y-2">
            <div>
              <div className="text-[12px] font-medium text-ink-2">Chance de bater a meta</div>
              <div className="mt-1 text-[30px] font-bold leading-none tracking-tight tabular-nums text-ink">
                {pct(d.probability, 0)}
              </div>
            </div>
            <ClassBadge value={d.classification} large />
          </div>
          <FeasibilityRange
            a={{ p10: d.p10, p50: d.p50, p90: d.p90, target: d.target, budget: d.budget }}
            f={money}
          />
        </>,
      );
    }
    case "decision_table": {
      const d = visualData<"decision_table">(chapter);
      return block(
        <DecisionTable rows={d.rows ?? []} horizonMonths={horizonMonths} />,
        "Ordenadas por impacto. Os impactos se sobrepõem e não devem ser somados.",
      );
    }
    default:
      return null;
  }
}

export default ChapterVisual;
