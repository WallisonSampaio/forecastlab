import clsx from "clsx";
import { ExternalLink } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { NoRunState } from "../components/RunControls";
import { Card, Loader, PageHeader, SeverityBadge } from "../components/ui";
import { useGet } from "../hooks/useApi";
import { money } from "../lib/format";
import type { Alert } from "../types";

interface AlertsData {
  summary: { total: number; by_severity: Record<string, number>; by_type: Record<string, number> };
  alerts: Alert[];
}

const TYPE_LABEL: Record<string, string> = {
  high_error: "🔴 High Forecast Error",
  severe_over: "🔴 Severe Overforecast",
  severe_under: "🔵 Severe Underforecast",
  target_above_p90: "🟠 Target Above P90",
  structural_change: "🟠 Forecast Structural Change",
  challenger_improving: "🟡 Challenger Model Improving",
  opportunity: "🟢 Commercial Opportunity",
};

const BORDER: Record<string, string> = {
  red: "border-l-[#d03b3b]",
  blue: "border-l-[#2a78d6]",
  orange: "border-l-[#ec835a]",
  yellow: "border-l-[#fab219]",
  green: "border-l-[#0ca30c]",
};

export default function Alerts() {
  const [type, setType] = useState<string>("");
  const [severity, setSeverity] = useState<string>("");
  const { data, isLoading } = useGet<AlertsData>("/api/alerts", {
    type: type || undefined,
    severity: severity || undefined,
  });
  if (isLoading) return <Loader />;
  if (!data) return <NoRunState />;
  return (
    <div>
      <PageHeader
        eyebrow="Alert center"
        title="Exceptions that need attention"
        subtitle="Each alert explains the issue, the affected entity, its magnitude and potential impact, and what to investigate."
      />
      <div className="grid gap-5 xl:grid-cols-[280px_1fr]">
        <div className="flex flex-col gap-4">
          <Card title="By type">
            <ul className="space-y-1">
              <li>
                <button
                  type="button"
                  onClick={() => setType("")}
                  className={clsx(
                    "flex w-full justify-between rounded-md px-2 py-1.5 text-sm",
                    !type && "bg-slate-100 font-semibold",
                  )}
                >
                  All alerts <span>{data.summary.total}</span>
                </button>
              </li>
              {Object.entries(data.summary.by_type).map(([k, v]) => (
                <li key={k}>
                  <button
                    type="button"
                    onClick={() => setType(k)}
                    className={clsx(
                      "flex w-full justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-slate-50",
                      type === k && "bg-slate-100 font-semibold",
                    )}
                  >
                    <span>{TYPE_LABEL[k] ?? k}</span>
                    <span className="text-muted">{v}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="By severity">
            <div className="flex flex-wrap gap-2">
              {["", "critical", "high", "medium", "low"].map((s) => (
                <button
                  key={s || "all"}
                  type="button"
                  onClick={() => setSeverity(s)}
                  className={clsx(
                    "rounded-full border px-3 py-1 text-xs font-medium",
                    severity === s
                      ? "border-ink bg-ink text-white"
                      : "border-line text-ink-2 hover:bg-slate-50",
                  )}
                >
                  {s ? `${s} (${data.summary.by_severity[s] ?? 0})` : "all"}
                </button>
              ))}
            </div>
          </Card>
        </div>
        <div className="flex flex-col gap-3">
          {data.alerts.length === 0 && <Card>No alerts for this selection.</Card>}
          {data.alerts.map((a) => (
            <div key={a.id} className={clsx("card border-l-4 p-4", BORDER[a.color])}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold">
                  <span aria-hidden>{a.icon}</span> {a.title}
                </span>
                <SeverityBadge value={a.severity} />
                <span className="ml-auto text-xs text-muted">
                  Potential impact <b className="text-ink">{money(a.potential_impact)}</b>
                </span>
              </div>
              <div className="mt-2 grid gap-3 text-sm md:grid-cols-[1fr_1fr]">
                <div>
                  <div className="label-xs">Issue</div>
                  <div className="mt-0.5">{a.issue}</div>
                  <div className="label-xs mt-2">Affected entity</div>
                  <div className="mt-0.5">
                    {[a.entity.customer, a.entity.sku, a.entity.product, a.entity.region]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                  <div className="label-xs mt-2">Magnitude</div>
                  <div className="mt-0.5 font-semibold">{a.magnitude}</div>
                </div>
                <div>
                  <div className="label-xs">Explanation</div>
                  <div className="mt-0.5 text-ink-2">{a.explanation}</div>
                  <div className="label-xs mt-2">Recommended investigation</div>
                  <div className="mt-0.5 text-ink-2">{a.recommendation}</div>
                </div>
              </div>
              <Link
                to={`/app/ai?q=${encodeURIComponent(
                  a.type === "target_above_p90"
                    ? `Is the target realistic for ${a.entity.customer}?`
                    : `Which model performs best for ${a.entity.sku ?? ""} at ${a.entity.customer}?`,
                )}`}
                className="mr-4 mt-3 inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline"
              >
                Ask the AI analyst
              </Link>
              {a.entity.series_id && (
                <Link
                  to={`/app/forecasting?mode=series&series=${encodeURIComponent(a.entity.series_id)}`}
                  className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline"
                >
                  Open in Forecast Workspace <ExternalLink size={12} />
                </Link>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
