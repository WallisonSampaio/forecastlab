import clsx from "clsx";
import { RefreshCw } from "lucide-react";

import { runProgressPct, useJourney } from "../../hooks/useJourney";
import type { JourneyStatus } from "../../types/journey";

/**
 * Slim notice shown on the three journey pages while a new run is in progress over an active one
 * (`run.rerunning`, spec §1.5). Renders nothing otherwise. Without the `journey` prop it reads
 * `useJourney()` itself.
 */
export function RerunBanner({ journey, className }: { journey?: JourneyStatus | null; className?: string }) {
  const own = useJourney({ enabled: !journey });
  const run = (journey ?? own.data)?.run;
  if (!run?.rerunning) return null;
  return (
    <div
      role="status"
      className={clsx(
        "flex items-start gap-2.5 rounded-2xl border border-[#d6e6ff] bg-[#eef5ff] px-4 py-2.5 text-[13px] leading-snug text-[#1f4f9e]",
        className,
      )}
    >
      <RefreshCw size={15} className="mt-0.5 shrink-0 animate-spin [animation-duration:2.4s]" aria-hidden />
      <span className="min-w-0 break-words">
        Nova execução em andamento ({runProgressPct(run.progress)}%) — os números abaixo são da execução{" "}
        <span className="font-semibold">{run.run_id ?? "atual"}</span> e serão atualizados ao final.
      </span>
    </div>
  );
}

export default RerunBanner;
