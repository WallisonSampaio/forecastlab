import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { full } from "../lib/format";
import { api } from "../services/api";
import type { JourneyRun, JourneyStatus } from "../types/journey";

export const JOURNEY_PATH = "/api/journey";
/** Same key shape as `useGet(path, params)`, so both share the cache. */
export const JOURNEY_KEY = [JOURNEY_PATH, {}] as const;

/** Poll intervals (spec §1.2): 1,5 s while a run is in progress, otherwise 30 s. */
export const JOURNEY_POLL_RUNNING_MS = 1500;
export const JOURNEY_POLL_IDLE_MS = 30_000;

/**
 * Per QueryClient: `dataUpdatedAt` of the journey response whose run completion already refreshed the
 * app. Several components use `useJourney` at once (sidebar, page, gate, banner); only the first one
 * that sees a completion invalidates, so every query is refetched once, not once per instance.
 */
const completionHandled = new WeakMap<QueryClient, number>();

/**
 * Journey state (`GET /api/journey`, spec §1.2/§1.5). Polls every 1,5 s while a run is in progress,
 * otherwise every 30 s. When a run goes from running to completed, every other query is invalidated
 * once (same pattern as `useJob`). `enabled: false` turns the request off (e.g. a component that
 * received the journey as a prop).
 */
export function useJourney(options?: { enabled?: boolean }) {
  const qc = useQueryClient();
  const query = useQuery<JourneyStatus, Error>({
    queryKey: JOURNEY_KEY,
    queryFn: () => api.get<JourneyStatus>(JOURNEY_PATH),
    refetchInterval: (q) =>
      q.state.data?.run.state === "running" ? JOURNEY_POLL_RUNNING_MS : JOURNEY_POLL_IDLE_MS,
    placeholderData: (prev) => prev,
    enabled: options?.enabled ?? true,
  });
  const state = query.data?.run.state;
  const updatedAt = query.dataUpdatedAt;
  const wasRunning = useRef(false);
  useEffect(() => {
    if (wasRunning.current && state === "completed" && completionHandled.get(qc) !== updatedAt) {
      completionHandled.set(qc, updatedAt);
      qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== JOURNEY_PATH });
    }
    wasRunning.current = state === "running";
  }, [state, updatedAt, qc]);
  return query;
}

/** True when the journey reached `pronto` (an active completed run exists). */
export const isJourneyReady = (j: JourneyStatus | null | undefined) => j?.stage === "pronto";

/** Run progress fraction (0–1, null while unknown) -> integer percentage 0–100 for "{step} · {pct}%". */
export function runProgressPct(progress: number | null | undefined): number {
  return Math.round(Math.min(1, Math.max(0, progress ?? 0)) * 100);
}

/**
 * Progress line of a running job (spec §1.5): "{done} de {total} séries · {pct}%", or
 * "{step} · {pct}%" while queued (done/total are still null).
 */
export function runProgressLine(run: Pick<JourneyRun, "progress" | "step" | "done" | "total">): string {
  const pct = runProgressPct(run.progress);
  if (run.done != null && run.total != null)
    return `${full(run.done)} de ${full(run.total)} séries · ${pct}%`;
  return `${run.step ?? "Preparando a execução"} · ${pct}%`;
}
