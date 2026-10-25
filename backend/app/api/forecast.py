"""Forecasting endpoints: runs, workspace, hierarchy, model performance, overrides."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app import db
from app.forecasting.models import model_catalog
from app.forecasting.worker import RunParams
from app.services import overrides, runs
from app.services.context import PlanningContext, invalidate
from app.services.forecast_views import (
    aggregate_view,
    heatmap,
    hierarchy_table,
    leaderboard,
    model_distribution,
    performance_table,
    registry,
    series_detail,
    series_list,
)

from .deps import ctx_dep, filters_dep, measure_param

router = APIRouter(prefix="/api", tags=["forecasting"])


class RunRequest(BaseModel):
    horizon: int = Field(12, description="Forecast horizon in months (3, 6, 12, 18 or 24)")
    n_folds: int = Field(4, ge=1, le=8)
    fold_horizon: int = Field(3, ge=1, le=12)
    clean_stockouts: bool = True
    run_all_models: bool = False
    models: list[str] = Field(default_factory=list)


class OverrideRequest(BaseModel):
    customer: str | None = None
    sku: str | None = None
    date: str
    event_type: str
    uplift_pct: float
    comment: str | None = ""
    created_by: str | None = "Demand Planner"


@router.post("/forecast/run")
def run(req: RunRequest) -> dict[str, Any]:
    if req.horizon not in (3, 6, 12, 18, 24):
        raise HTTPException(400, "horizon must be one of 3, 6, 12, 18, 24")
    try:
        run_id = runs.start_run(RunParams(**req.model_dump()))
    except runs.RunBlockedError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"run_id": run_id}


@router.get("/forecast/runs")
def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    from app.services.context import clean

    return clean(runs.list_runs(limit))


@router.get("/forecast/job")
def current_job() -> dict[str, Any] | None:
    from app.services.context import clean

    return clean(runs.current_job())


@router.get("/forecast/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    from app.services.context import clean

    job = runs.get_job(run_id)
    if job is None:
        raise HTTPException(404, "Run not found")
    return clean(job)


@router.post("/forecast/runs/{run_id}/activate")
def activate_run(run_id: str) -> dict[str, Any]:
    owner = db.scalar("SELECT dataset_version FROM forecast_runs WHERE run_id = ? AND status = 'completed'", [run_id])
    if not owner:
        raise HTTPException(404, "Completed run not found")
    from app.services import datasets

    if owner != datasets.active_version():
        datasets.activate(owner)
    db.set_state("active_run", run_id)
    invalidate()
    return {"run_id": run_id, "dataset_version": owner}


@router.get("/forecast/models")
def models() -> list[dict[str, Any]]:
    return model_catalog()


@router.get("/forecast/series")
def series(filters: dict = Depends(filters_dep), ctx: PlanningContext = Depends(ctx_dep)) -> list[dict[str, Any]]:
    return series_list(ctx, filters)


@router.get("/forecast/series-detail")
def detail(
    series_id: str, measure: str = Depends(measure_param), ctx: PlanningContext = Depends(ctx_dep)
) -> dict[str, Any]:
    try:
        return series_detail(ctx, series_id, measure)
    except KeyError as exc:
        raise HTTPException(404, f"Series '{series_id}' not found") from exc


@router.get("/forecast/aggregate")
def aggregate(
    measure: str = Depends(measure_param), filters: dict = Depends(filters_dep), ctx: PlanningContext = Depends(ctx_dep)
) -> dict[str, Any]:
    return aggregate_view(ctx, filters, measure)


@router.get("/forecast/hierarchy")
def hierarchy(
    level: str = "region",
    method: str = Query("bottom_up", pattern="^(bottom_up|top_down)$"),
    measure: str = Depends(measure_param),
    filters: dict = Depends(filters_dep),
    ctx: PlanningContext = Depends(ctx_dep),
) -> dict[str, Any]:
    try:
        return hierarchy_table(ctx, level, filters, measure, method)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/models/leaderboard")
def models_leaderboard(
    filters: dict = Depends(filters_dep), ctx: PlanningContext = Depends(ctx_dep)
) -> list[dict[str, Any]]:
    return leaderboard(ctx, filters)


@router.get("/models/distribution")
def models_distribution(filters: dict = Depends(filters_dep), ctx: PlanningContext = Depends(ctx_dep)):
    return model_distribution(ctx, filters)


@router.get("/models/heatmap")
def models_heatmap(
    metric: str = Query("wmape", pattern="^(wmape|bias)$"),
    filters: dict = Depends(filters_dep),
    ctx: PlanningContext = Depends(ctx_dep),
) -> dict[str, Any]:
    return heatmap(ctx, metric, filters)


@router.get("/models/performance")
def models_performance(filters: dict = Depends(filters_dep), ctx: PlanningContext = Depends(ctx_dep)):
    return performance_table(ctx, filters)


@router.get("/models/registry")
def models_registry(
    series_id: str | None = None, limit: int = Query(500, le=5000), ctx: PlanningContext = Depends(ctx_dep)
):
    return registry(ctx, series_id, limit)


@router.get("/overrides")
def list_overrides() -> list[dict[str, Any]]:
    return overrides.list_overrides()


@router.get("/overrides/event-library")
def event_library() -> list[dict[str, Any]]:
    return overrides.EVENT_LIBRARY


@router.post("/overrides")
def create_override(req: OverrideRequest) -> dict[str, Any]:
    try:
        return overrides.create_override(req.model_dump())
    except overrides.OverrideError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.put("/overrides/{override_id}")
def update_override(override_id: str, req: OverrideRequest) -> dict[str, Any]:
    try:
        return overrides.update_override(override_id, req.model_dump())
    except overrides.OverrideError as exc:
        raise HTTPException(400, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, "Override not found") from exc


@router.delete("/overrides/{override_id}")
def delete_override(override_id: str) -> dict[str, str]:
    try:
        overrides.delete_override(override_id)
    except KeyError as exc:
        raise HTTPException(404, "Override not found") from exc
    return {"deleted": override_id}
