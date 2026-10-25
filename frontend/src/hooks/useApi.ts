import { useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { api, type Params } from "../services/api";
import type { Job } from "../types";

/** GET helper bound to react-query; the key is the path + params. */
export function useGet<T>(
  path: string | null,
  params?: Params,
  options?: Omit<UseQueryOptions<T, Error>, "queryKey" | "queryFn">,
) {
  return useQuery<T, Error>({
    queryKey: [path, params ?? {}],
    queryFn: () => api.get<T>(path as string, params),
    enabled: path !== null && (options?.enabled ?? true),
    placeholderData: (prev) => prev,
    ...options,
  });
}

/** Polls the current forecast job and refreshes every query when it finishes. */
export function useJob() {
  const qc = useQueryClient();
  const query = useQuery<Job | null, Error>({
    queryKey: ["job"],
    queryFn: () => api.get<Job | null>("/api/forecast/job"),
    refetchInterval: (q) => (q.state.data ? 1500 : 8000),
  });
  const wasRunning = useRef(false);
  useEffect(() => {
    const running = !!query.data && ["queued", "running"].includes(query.data.status);
    if (wasRunning.current && !running) {
      qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "job" });
    }
    wasRunning.current = running;
  }, [query.data, qc]);
  return query;
}
