import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Activity, FileSpreadsheet, FileText, Play } from "lucide-react";
import { useState } from "react";

import { useJob } from "../hooks/useApi";
import { useFilters } from "../hooks/useFilters";
import { JOURNEY_KEY } from "../hooks/useJourney";
import { api, type Params } from "../services/api";
import type { Filters } from "../types";
import { EmptyState, ErrorState, Field, Modal, ProgressBar } from "./ui";

export function RunForecastButton({ label = "Rodar forecast" }: { label?: string }) {
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
      // The journey polls every 30 s while idle: refresh it now so the stepper shows the run at once.
      qc.invalidateQueries({ queryKey: JOURNEY_KEY });
      setOpen(false);
    },
  });
  const busy = !!job;
  return (
    <>
      <button type="button" className="btn-primary" disabled={busy} onClick={() => setOpen(true)}>
        {busy ? <Activity size={16} className="animate-pulse" /> : <Play size={16} />}
        {busy ? "Forecast em execução…" : label}
      </button>
      <Modal open={open} title="Rodar forecast" onClose={() => setOpen(false)}>
        <div className="space-y-4">
          <p className="text-sm text-muted">
            Analisa o perfil de cada série Cliente × SKU, seleciona os modelos candidatos, executa o backtest
            com origem móvel, escolhe Campeão e Desafiante e gera o forecast P10/P50/P90.
          </p>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Horizonte do forecast">
              <select className="input" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
                {[3, 6, 12, 18, 24].map((h) => (
                  <option key={h} value={h}>
                    {h} meses
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Janelas de backtest">
              <select className="input" value={folds} onChange={(e) => setFolds(Number(e.target.value))}>
                {[2, 3, 4, 5, 6].map((h) => (
                  <option key={h} value={h}>
                    {h}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Meses por janela">
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
            <input type="checkbox" checked={clean} onChange={(e) => setClean(e.target.checked)} /> Corrigir
            meses com ruptura no treino (demanda irrestrita)
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Desligar o
            roteador de modelos — rodar os 15 modelos em todas as séries (mais lento)
          </label>
          <ErrorState error={run.error} />
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>
              Cancelar
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() => run.mutate()}
              disabled={run.isPending}
            >
              <Play size={16} /> Iniciar execução
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
        title={job ? "Forecast em execução" : "Ainda não há forecast"}
        icon={<Activity className={job ? "animate-pulse" : ""} />}
      >
        {job ? (
          <div className="w-80">
            <div className="mb-2 text-xs">{job.step}</div>
            <ProgressBar value={job.progress} />
            <div className="mt-1 text-xs">{Math.round(job.progress * 100)}%</div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <span>Rode o motor de forecast para testar os modelos e gerar o plano de 12 meses.</span>
            <RunForecastButton />
          </div>
        )}
      </EmptyState>
    </div>
  );
}

/**
 * Excel export + the executive report download ("Baixar relatório (HTML)", spec §2.2.1): the same
 * 7-chapter story as the screen. `scope` (the report scope) overrides the global filters when given.
 */
export function ExportMenu({ scope }: { scope?: Filters } = {}) {
  const { filters } = useFilters();
  const active: Params = { ...(scope ?? filters) };
  return (
    <div className="flex flex-wrap gap-2">
      <a className="btn-secondary" href={api.url("/api/export/excel", active)}>
        <FileSpreadsheet size={15} className="text-emerald-600" /> Excel
      </a>
      <a
        className="btn-secondary"
        href={api.url("/api/export/executive-html", { download: true, ...active })}
        download
      >
        <FileText size={15} className="text-brand" /> Baixar relatório (HTML)
      </a>
    </div>
  );
}
