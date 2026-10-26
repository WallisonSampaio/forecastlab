import { ChevronRight } from "lucide-react";
import { Fragment } from "react";
import { Link } from "react-router-dom";

import type { DeviationUrlState } from "../../lib/deviationsUrl";
import type { Takeaway } from "../../types/story";
import { Card } from "../ui";

/** Most takeaways a chapter shows (spec §4.5: ≤ 3). */
export const MAX_TAKEAWAYS = 3;

/**
 * Renders the backend's `**…**` emphasis as `<strong>` without injecting HTML: the text is split on
 * `**` and alternates plain and strong runs. An unmatched trailing `**` is dropped and its text stays
 * plain, so a malformed string never bolds the rest of the sentence.
 */
export function Emphasis({ text }: { text: string }) {
  const parts = text.split("**");
  const balanced = parts.length % 2 === 1;
  return (
    <>
      {parts.map((part, i) => {
        if (!part) return null;
        const strong = i % 2 === 1 && (balanced || i < parts.length - 1);
        return strong ? (
          <strong key={i} className="font-semibold text-ink">
            {part}
          </strong>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        );
      })}
    </>
  );
}

/**
 * "Leituras" (spec §2.2.1): the chapter's numbered takeaways (1–3), each optionally linking to the
 * deep dive. A text card: it carries no `data-visual`.
 */
export function Takeaways({
  items,
  hrefOf,
  className,
}: {
  items: Takeaway[];
  /** Deep-dive href of a takeaway link (adds the report scope and the origin chapter). */
  hrefOf: (params: Partial<DeviationUrlState>) => string;
  className?: string;
}) {
  const shown = items.slice(0, MAX_TAKEAWAYS);
  if (!shown.length) return null;
  return (
    <Card title="Leituras" className={className}>
      <ol className="divide-y divide-line" aria-label="Leituras do capítulo">
        {shown.map((tk, i) => (
          <li key={i} className="flex gap-3.5 py-4 first:pt-0 last:pb-0" data-takeaway>
            <span
              aria-hidden
              className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-line bg-white text-[12px] font-bold tabular-nums text-ink shadow-[0_2px_6px_-3px_rgba(45,50,119,0.25)]"
            >
              {i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className="break-words text-[14px] leading-relaxed text-ink-2">
                <Emphasis text={tk.text} />
              </p>
              {tk.link && (
                <Link
                  to={hrefOf(tk.link.params)}
                  className="mt-1.5 inline-flex items-center gap-0.5 rounded-md text-[12.5px] font-semibold text-brand hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/60"
                >
                  {tk.link.label || "Ver no deep dive"}
                  <ChevronRight size={14} aria-hidden />
                </Link>
              )}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

export default Takeaways;
