"""Forecast run jobs (background thread) + Forecast Run Registry."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import traceback
from dataclasses import asdict
from datetime import datetime
from typing import Any

import pandas as pd

from app import db
from app.forecasting.engine import ENGINE_VERSION, run_engine
from app.forecasting.models import MODEL_REGISTRY
from app.forecasting.worker import RunParams
from app.services import datasets

log = logging.getLogger("forecastlab.runs")

_jobs: dict[str, dict[str, Any]] = {}
_run_lock = threading.Lock()

COMPLETED = "Concluído"
_LEGACY_FALLBACK = re.compile(r"^(\d+) series fell back to Naive$")


class RunBlockedError(RuntimeError):
    pass


def _new_run_id() -> str:
    return f"RUN-{datetime.now():%Y%m%d-%H%M%S}"


def active_run_id() -> str | None:
    return db.get_state("active_run")


def latest_successful_run(version: str) -> str | None:
    v = db.scalar(
        "SELECT run_id FROM forecast_runs WHERE dataset_version = ? AND status = 'completed' "
        "ORDER BY created_at DESC LIMIT 1",
        [version],
    )
    return str(v) if v else None


def current_job() -> dict[str, Any] | None:
    running = [j for j in _jobs.values() if j["status"] in ("queued", "running")]
    return running[0] if running else None


def get_job(run_id: str) -> dict[str, Any] | None:
    if run_id in _jobs:
        return dict(_jobs[run_id])
    df = db.query_df("SELECT * FROM forecast_runs WHERE run_id = ?", [run_id])
    if df.empty:
        return None
    return _run_row(df.iloc[0].to_dict())


def _completed_message(n_fallback: int) -> str:
    if not n_fallback:
        return COMPLETED
    return f"{COMPLETED} - {n_fallback} série(s) usaram o modelo Naive como contingência"


def _localize_message(msg: Any) -> Any:
    """Run messages stored by older (English) versions -> Portuguese."""
    if not isinstance(msg, str):
        return msg
    if msg == "OK":
        return COMPLETED
    m = _LEGACY_FALLBACK.match(msg)
    return _completed_message(int(m.group(1))) if m else msg


def _run_row(r: dict[str, Any]) -> dict[str, Any]:
    r["params"] = json.loads(r.pop("params_json") or "{}")
    r["summary"] = json.loads(r.pop("summary_json") or "{}")
    r["progress"] = 1.0 if r["status"] == "completed" else 0.0
    r["message"] = _localize_message(r.get("message"))
    return r


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    df = db.query_df("SELECT * FROM forecast_runs ORDER BY created_at DESC LIMIT ?", [limit])
    rows = [_run_row(r) for r in df.to_dict("records")]
    live = {j["run_id"]: j for j in _jobs.values() if j["status"] in ("queued", "running")}
    return [live.pop(r["run_id"], r) for r in rows] + list(live.values())


def start_run(
    params: RunParams | None = None, dataset_version: str | None = None, wait: bool = False, workers: int | None = None
) -> str:
    params = params or RunParams()
    version = dataset_version or datasets.active_version()
    if not version:
        raise RunBlockedError("Nenhuma base ativa. Carregue um arquivo ou a base de demonstração primeiro.")
    ds = datasets.get_dataset(version)
    if ds is None or ds["status"] == "blocked":
        raise RunBlockedError("Execução do forecast bloqueada: a base tem erros críticos de validação.")
    unknown = [m for m in params.models if m not in MODEL_REGISTRY]
    if unknown:
        raise ValueError(f"Modelo(s) desconhecido(s): {', '.join(unknown)}")
    if not _run_lock.acquire(blocking=False):
        raise RunBlockedError("Já existe uma execução de forecast em andamento.")
    run_id = _new_run_id()
    while run_id in _jobs or db.scalar("SELECT 1 FROM forecast_runs WHERE run_id = ?", [run_id]):
        time.sleep(1)
        run_id = _new_run_id()
    job = {
        "run_id": run_id,
        "dataset_version": version,
        "status": "queued",
        "progress": 0.0,
        "step": "Na fila",
        "created_at": datetime.now(),
        "horizon": params.horizon,
        "params": asdict(params),
        "model_version": ENGINE_VERSION,
        "scenario": "Base",
    }
    _jobs[run_id] = job
    db.insert_df(
        "forecast_runs",
        pd.DataFrame(
            [
                {
                    "run_id": run_id,
                    "created_at": job["created_at"],
                    "dataset_version": version,
                    "horizon": params.horizon,
                    "model_version": ENGINE_VERSION,
                    "scenario": "Base",
                    "status": "running",
                    "params_json": json.dumps(asdict(params)),
                    "summary_json": "{}",
                    "message": "",
                }
            ]
        ),
    )
    thread = threading.Thread(
        target=_execute, args=(run_id, version, params, workers), daemon=True, name=f"forecast-{run_id}"
    )
    thread.start()
    if wait:
        thread.join()
    return run_id


def _execute(run_id: str, version: str, params: RunParams, workers: int | None) -> None:
    job = _jobs[run_id]
    job["status"] = "running"
    t0 = time.perf_counter()

    def progress(done: int, total: int, step: str) -> None:
        job["progress"] = round(0.05 + 0.85 * done / max(total, 1), 4)
        job["step"] = step
        job["done"] = done
        job["total"] = total

    try:
        sales = datasets.get_sales(version)
        out = run_engine(sales, params, progress, workers=workers)
        job["step"] = "Salvando resultados no registro de modelos"
        job["progress"] = 0.93
        _persist(run_id, version, out)
        summary = _summary(out)
        duration = time.perf_counter() - t0
        with db.locked() as con:
            con.execute(
                "UPDATE forecast_runs SET status='completed', finished_at=?, duration_s=?, n_series=?, n_models=?, "
                "summary_json=?, message=? WHERE run_id=?",
                [
                    datetime.now(),
                    duration,
                    out.n_series,
                    out.n_models,
                    json.dumps(summary, default=str),
                    _completed_message(len(out.errors)),
                    run_id,
                ],
            )
        if datasets.active_version() == version:
            db.set_state("active_run", run_id)
        from app.services import context

        context.invalidate()
        if datasets.active_version() == version:
            try:  # re-anchor preset scenarios (promo months) to the new horizon
                from app.scenarios.store import ensure_presets, refresh_presets

                ctx = context.get_context()
                ensure_presets(ctx)
                refresh_presets(ctx)
            except Exception:
                log.exception("Could not refresh scenario presets")
        job.update(
            status="completed",
            progress=1.0,
            step=COMPLETED,
            duration_s=duration,
            summary=summary,
            message=_completed_message(len(out.errors)),
        )
    except Exception as exc:
        log.exception("Forecast run %s failed", run_id)
        job.update(status="failed", step="Falhou", message=f"A execução falhou: {exc}")
        db.execute(
            "UPDATE forecast_runs SET status='failed', finished_at=?, message=? WHERE run_id=?",
            [datetime.now(), f"A execução falhou: {exc}\n{traceback.format_exc()[-1500:]}", run_id],
        )
    finally:
        _run_lock.release()


def _persist(run_id: str, version: str, out) -> None:
    now = datetime.now()
    sales_end = datasets.get_sales(version)["date"].max()
    sel = out.selection.copy()
    sel["run_id"] = run_id
    prof = out.profiles.copy()
    prof["run_id"] = run_id
    reg = out.registry.copy()
    reg["run_id"] = run_id
    reg["model_version"] = reg["model"].map(lambda m: MODEL_REGISTRY[m].version)
    reg["training_date"] = now
    reg["data_cutoff"] = sales_end
    bt = out.backtest.copy()
    bt["run_id"] = run_id
    fc = out.forecasts.copy()
    fc["run_id"] = run_id
    for table, df in (
        ("series_selection", sel),
        ("series_profiles", prof),
        ("model_registry", reg),
        ("backtest_results", bt),
        ("forecasts", fc),
    ):
        db.insert_df(table, df)


def _summary(out) -> dict[str, Any]:
    sel = out.selection
    bt = out.backtest.merge(
        sel[["series_id", "champion"]], left_on=["series_id", "model"], right_on=["series_id", "champion"]
    )
    total = bt["actual"].abs().sum()
    wm = float((bt["forecast"] - bt["actual"]).abs().sum() / total) if total else None
    bias = float((bt["forecast"] - bt["actual"]).sum() / bt["actual"].sum()) if total else None
    return {
        "wmape": wm,
        "bias": bias,
        "accuracy": None if wm is None else max(0.0, 1 - wm),
        "champions": sel["champion"].value_counts().to_dict(),
        "series_types": sel["series_type"].value_counts().to_dict(),
        "confidence": sel["confidence"].value_counts().to_dict(),
        "duration_s": round(out.duration_s, 1),
        "errors": out.errors[:20],
    }
