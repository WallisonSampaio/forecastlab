import clsx from "clsx";
import { Link } from "react-router-dom";

import type { ChapterId } from "../../lib/deviationsUrl";
import type { Chapter } from "../../types/story";
import { ProgressBar } from "../ui";

/**
 * Sticky chapter rail (spec §2.2.1): a wrapping row of the 7 chapter chips, a thin progress bar and
 * "Capítulo {n} de 7". Chips are links that replace the history entry (chapter state lives in the
 * URL path). Chapters without data (`status: "empty"`) are muted but stay clickable.
 * Below the topbar it sticks at 76 px; in presentation mode (no topbar) at the top.
 */
export function ChapterRail({
  chapters,
  currentId,
  hrefOf,
  presenting = false,
}: {
  chapters: Pick<Chapter, "id" | "short" | "status">[];
  currentId: ChapterId;
  hrefOf: (id: ChapterId) => string;
  presenting?: boolean;
}) {
  const total = chapters.length;
  const pos = Math.max(
    0,
    chapters.findIndex((c) => c.id === currentId),
  );
  const n = pos + 1;
  return (
    <nav
      aria-label="Capítulos"
      className={clsx("sticky z-20 mb-7", presenting ? "top-0 pt-2" : "top-[76px]")}
    >
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2.5 rounded-2xl border border-white/80 bg-white/85 px-2.5 py-2 shadow-[0_10px_28px_-16px_rgba(45,50,119,0.35)] backdrop-blur-xl">
        <ol className="flex min-w-[240px] flex-[1_1_0%] flex-wrap gap-1">
          {chapters.map((ch, i) => {
            const current = i === pos;
            const done = i < pos;
            const empty = ch.status === "empty";
            return (
              <li key={ch.id}>
                <Link
                  to={hrefOf(ch.id)}
                  replace
                  aria-current={current ? "step" : undefined}
                  data-chapter={ch.id}
                  data-empty={empty || undefined}
                  className={clsx(
                    "inline-flex items-center gap-2 whitespace-nowrap rounded-xl py-1.5 pl-1.5 pr-3 text-[13px] font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/60",
                    current
                      ? "bg-gradient-to-r from-[#3483fa] to-[#5b9cff] text-white shadow-[0_8px_18px_-10px_rgba(52,131,250,0.9)]"
                      : empty
                        ? "text-muted/80 hover:bg-[#f4f7ff] hover:text-ink-2"
                        : "text-ink-2 hover:bg-[#f4f7ff] hover:text-ink",
                  )}
                >
                  <span
                    aria-hidden
                    className={clsx(
                      "flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-bold tabular-nums",
                      current && "bg-white/25 text-white",
                      !current && done && !empty && "bg-[#e6efff] text-brand",
                      !current && !done && !empty && "bg-[#eef1fa] text-ink-2",
                      !current && empty && "border border-dashed border-[#c9cee0] text-muted",
                    )}
                  >
                    {i + 1}
                  </span>
                  {ch.short}
                  {empty && <span className="sr-only"> (sem dados nesta base)</span>}
                </Link>
              </li>
            );
          })}
        </ol>
        <div className="flex shrink-0 items-center gap-3 pr-2">
          <span
            className="whitespace-nowrap text-[12px] font-semibold tabular-nums text-ink-2"
            aria-live="polite"
          >
            Capítulo {n} de {total}
          </span>
          <ProgressBar value={total ? n / total : 0} className="h-1.5 w-24" />
        </div>
      </div>
    </nav>
  );
}

export default ChapterRail;
