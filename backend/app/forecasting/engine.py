"""Forecast run orchestration (parallel across series)."""

from __future__ import annotations

import json
import logging
import math
import multiprocessing
import os
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .panel import build_panel
from .worker import RunParams, process_series_safe

log = logging.getLogger("forecastlab.engine")
ENGINE_VERSION = "forecastlab-engine 1.0.0"

ProgressFn = Callable[[int, int, str], None]


@dataclass
class EngineOutput:
    selection: pd.DataFrame
    profiles: pd.DataFrame
    registry: pd.DataFrame
    backtest: pd.DataFrame
    forecasts: pd.DataFrame
    duration_s: float
    n_series: int
    n_models: int
    errors: list[dict[str, str]]


def default_workers() -> int:
    env = os.getenv("FORECASTLAB_WORKERS")
    if env:
        return max(1, int(env))
    return max(1, min(8, (os.cpu_count() or 2) - 1))


_BLAS_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")


def _init_worker() -> None:
    """One BLAS thread per worker process - avoids massive oversubscription."""
    try:
        from threadpoolctl import threadpool_limits

        threadpool_limits(1)
    except Exception:
        pass


def _clean(v: Any) -> Any:
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def run_engine(
    sales: pd.DataFrame,
    params: RunParams,
    progress: ProgressFn | None = None,
    workers: int | None = None,
) -> EngineOutput:
    t0 = time.perf_counter()
    progress = progress or (lambda done, total, step: None)
    progress(0, 1, "Building series panel")
    panel = build_panel(sales, params.horizon)
    total = len(panel)
    workers = workers if workers is not None else default_workers()
    results: list[dict[str, Any]] = []

    def _sequential(items):
        for s in items:
            results.append(process_series_safe(s, params))
            progress(len(results), total, f"Backtesting {s.series_id}")

    if workers > 1 and total >= 16:
        progress(0, total, f"Backtesting models on {total} series ({workers} workers)")
        for var in _BLAS_VARS:  # inherited by the spawned workers before numpy loads
            os.environ.setdefault(var, "1")
        try:
            # "spawn" everywhere: never fork a server process that holds threads and a DB handle.
            ctx = multiprocessing.get_context("spawn")
            with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker, mp_context=ctx) as ex:
                futures = {ex.submit(process_series_safe, s, params): s for s in panel}
                for fut in as_completed(futures):
                    results.append(fut.result())
                    progress(len(results), total, f"Backtesting {futures[fut].series_id}")
        except (BrokenProcessPool, OSError, RuntimeError) as exc:  # pragma: no cover - environment specific
            log.warning("Process pool unavailable (%s); running sequentially", exc)
            done = {r["series_id"] for r in results}
            _sequential([s for s in panel if s.series_id not in done])
    else:
        _sequential(panel)

    progress(total, total, "Assembling results")
    results.sort(key=lambda r: r["series_id"])
    sel_rows, prof_rows, reg_rows, bt_rows, fc_rows, errors = [], [], [], [], [], []
    for r in results:
        sid = r["series_id"]
        if r.get("error"):
            errors.append({"series_id": sid, "error": r["error"]})
        sel_rows.append(
            {
                "series_id": sid,
                "customer": r["customer"],
                "sku": r["sku"],
                "history_months": r["history_months"],
                "series_type": r["profile"]["series_type"],
                "champion": r["champion"],
                "challenger": r["challenger"],
                "wmape": _clean(r["wmape"]),
                "bias": _clean(r["bias"]),
                "rmse": _clean(r["rmse"]),
                "mase": _clean(r["mase"]),
                "challenger_wmape": _clean(r["challenger_wmape"]),
                "wmape_std": _clean(r["wmape_std"]),
                "confidence": r["confidence"],
                "confidence_score": r["confidence_score"],
                "candidates": json.dumps(r["candidates"]),
            }
        )
        p = r["profile"]
        prof_rows.append(
            {
                "series_id": sid,
                "customer": r["customer"],
                "sku": r["sku"],
                **{k: _clean(v) for k, v in p.items()},
                "candidate_models": json.dumps(r["candidates"]),
            }
        )
        for e in r["registry"]:
            reg_rows.append(
                {
                    "series_id": sid,
                    **{k: _clean(v) for k, v in e.items() if k not in ("parameters", "fold_wmape")},
                    "fold_wmape": json.dumps([round(x, 4) for x in e["fold_wmape"]]),
                    "parameters": json.dumps(e["parameters"], default=str),
                }
            )
        for b in r["backtest"]:
            bt_rows.append({"series_id": sid, **b})
        for f in r["forecasts"]:
            fc_rows.append({"series_id": sid, **f})

    n_models = len({row["model"] for row in reg_rows if row["status"] == "ok"})
    return EngineOutput(
        selection=pd.DataFrame(sel_rows),
        profiles=pd.DataFrame(prof_rows),
        registry=pd.DataFrame(reg_rows),
        backtest=pd.DataFrame(bt_rows),
        forecasts=pd.DataFrame(fc_rows),
        duration_s=time.perf_counter() - t0,
        n_series=total,
        n_models=n_models,
        errors=errors,
    )
