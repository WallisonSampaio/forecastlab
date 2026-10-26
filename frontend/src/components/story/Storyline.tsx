import { ChevronRight } from "lucide-react";
import { Link } from "react-router-dom";

import type { ChapterId } from "../../lib/deviationsUrl";
import type { Chapter, Story } from "../../types/story";
import { Card } from "../ui";

const SCQA_LINES: { key: keyof Story["scqa"]; label: string }[] = [
  { key: "situacao", label: "Situação" },
  { key: "complicacao", label: "Complicação" },
  { key: "resposta", label: "Resposta" },
];

/** Resumo: the SCQA as three short lines under the governing thought, each with a bold label. */
export function Scqa({ scqa }: { scqa: Story["scqa"] }) {
  const lines = SCQA_LINES.filter((l) => scqa[l.key]);
  if (!lines.length) return null;
  return (
    <dl
      className="max-w-[86ch] space-y-1.5 text-[14px] leading-relaxed text-ink-2"
      aria-label="Situação, complicação e resposta"
    >
      {lines.map((l) => (
        <div key={l.key} className="break-words">
          <dt className="inline font-semibold text-ink">{l.label}</dt>{" "}
          <dd className="inline">{scqa[l.key]}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * "O roteiro" (Resumo): the following chapters as a numbered list of their headlines, each a link to
 * that chapter (Minto's vertical logic: the governing thought above, its support below).
 * A text card: it carries no `data-visual`.
 */
export function Storyline({
  chapters,
  startAt,
  hrefOf,
}: {
  chapters: Chapter[];
  /** Number shown for the first chapter of the list (2 when it starts after the Resumo). */
  startAt: number;
  hrefOf: (id: ChapterId) => string;
}) {
  if (!chapters.length) return null;
  return (
    <Card title="O roteiro" subtitle="Cada capítulo sustenta a mensagem acima com uma conclusão e um número.">
      <ol className="-mx-3 divide-y divide-line">
        {chapters.map((ch, i) => {
          const empty = ch.status === "empty";
          return (
            <li key={ch.id}>
              <Link
                to={hrefOf(ch.id)}
                replace
                data-roteiro={ch.id}
                className="group flex items-start gap-3.5 rounded-xl px-3 py-3.5 transition hover:bg-[#f4f7ff] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/60"
              >
                <span
                  aria-hidden
                  className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-line bg-white text-[12px] font-bold tabular-nums text-ink"
                >
                  {startAt + i}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
                    {ch.short}
                  </span>
                  <span
                    className={
                      empty
                        ? "mt-0.5 block break-words text-[14px] leading-snug text-muted"
                        : "mt-0.5 block break-words text-[14.5px] font-medium leading-snug text-ink"
                    }
                  >
                    {empty ? (ch.notice ?? ch.title) : ch.headline}
                  </span>
                </span>
                <ChevronRight
                  size={16}
                  aria-hidden
                  className="mt-1 shrink-0 text-muted transition group-hover:translate-x-0.5 group-hover:text-brand"
                />
              </Link>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

export default Storyline;
