import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Activity, Download, Play } from "lucide-react";
import { useState } from "react";

import { useJob } from "../hooks/useApi";
import { useFilters } from "../hooks/useFilters";
import { api } from "../services/api";
import { EmptyState, ErrorState, Field, Modal, ProgressBar } from "./ui";

export function RunForecastButton({ label = "Run forecast" }: { label?: string }) {
  const [open, setOpen] = useState(false);
  const [horizon, setHorizon] = useState(12);
  const [folds, setFolds] = useState(4);
  const [foldH, setFoldH] = useState(3);
  const [clean, setClean] = useState(true);
  const [all, setAll] = useState(false);
  const qc = useQueryClient();
  const { data: job } = useJob();
  const run = useMutation({
    mutationFn: () =>
      api.post<{ run_id: string }>("/api/forecast/run", {
        horizon,
        n_folds: folds,
        fold_horizon: foldH,
        clean_stockouts: clean,
        run_all_models: all,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["job"] });
      setOpen(false);
    },
  });
  const busy = !!job;
  return (
    <>
      <button type="button" className="btn-primary" disabled={busy} onClick={() => setOpen(true)}>
        {busy ? <Activity size={16} className="animate-pulse" /> : <Play size={16} />}
        {busy ? "Forecast running…" : label}
      </button>
      <Modal open={open} title="Run forecast" onClose={() => setOpen(false)}>
        <div className="space-y-4">
          <p className="text-sm text-muted">
            Profiles every Customer × SKU series, routes candidate models, runs a rolling-origin backtest,
            selects Champion/Challenger and produces P10/P50/P90 forecasts.
          </p>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Forecast horizon">
              <select className="input" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
                {[3, 6, 12, 18, 24].map((h) => (
                  <option key={h} value={h}>
                    {h} months
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Backtest folds">
              <select className="input" value={folds} onChange={(e) => setFolds(Number(e.target.value))}>
                {[2, 3, 4, 5, 6].map((h) => (
                  <option key={h} value={h}>
                    {h}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Months per fold">
              <select className="input" value={foldH} onChange={(e) => setFoldH(Number(e.target.value))}>
                {[1, 2, 3, 4, 6].map((h) => (
                  <option key={h} value={h}>
                    {h}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={clean} onChange={(e) => setClean(e.target.checked)} /> Clean
            stock-out months in training (unconstrained demand)
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Disable model
            router — run all 15 models on every series (slower)
          </label>
          <ErrorState error={run.error} />
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() => run.mutate()}
              disabled={run.isPending}
            >
              <Play size={16} /> Start run
            </button>
          </div>
        </div>
      </Modal>
    </>
  );
}

/** Shown when the active dataset has no completed forecast run yet. */
export function NoRunState() {
  const { data: job } = useJob();
  return (
    <div className="card">
      <EmptyState
        title={job ? "Forecast run in progress" : "No forecast yet"}
        icon={<Activity size={20} className={job ? "animate-pulse text-brand" : ""} />}
      >
        {job ? (
          <div className="w-80">
            <div className="mb-2 text-xs">{job.step}</div>
            <ProgressBar value={job.progress} />
            <div className="mt-1 text-xs">{Math.round(job.progress * 100)}%</div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <span>Run the forecast engine to backtest the models and produce the 12-month plan.</span>
            <RunForecastButton />
          </div>
        )}
      </EmptyState>
    </div>
  );
}

export function ExportMenu() {
  const { filters } = useFilters();
  const q = new URLSearchParams(
    Object.entries(filters).filter(([, v]) => v) as [string, string][],
  ).toString();
  const suffix = q ? `?${q}` : "";
  return (
    <div className="flex gap-2">
      <a className="btn-secondary" href={`/api/export/excel${suffix}`}>
        <Download size={15} /> Excel
      </a>
      <a
        className="btn-secondary"
        href={`/api/export/executive-html${suffix}`}
        target="_blank"
        rel="noreferrer"
      >
        <Download size={15} /> Executive report
      </a>
    </div>
  );
}
