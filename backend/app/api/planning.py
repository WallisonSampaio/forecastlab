"""Scenario, S&OP, FVA, alerts, overview, semantic layer and AI endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.ai import analyst, llm
from app.alerts.engine import build_alerts, summary
from app.fva.fva import fva_report
from app.scenarios import store
from app.scenarios.elasticity import estimate_elasticities
from app.scenarios.engine import ScenarioParams, simulate
from app.semantic_layer.catalog import catalog
from app.services.context import PlanningContext, clean
from app.sop.allocation import allocate
from app.sop.cockpit import cockpit, overview
from app.sop.feasibility import assess, feasibility_by, probability_curve

from .deps import ctx_dep, filters_dep, require_run

router = APIRouter(prefix="/api", tags=["planning"])


class ScenarioRequest(BaseModel):
    name: str = "Custom scenario"
    description: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class SimulateRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)


class AllocationRequest(BaseModel):
    dimension: str = "region"
    method: str = "historical"
    total_target: float | None = None
    weights: dict[str, float] | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    measure: str = "revenue"


class AskRequest(BaseModel):
    question: str
    filters: dict[str, Any] = Field(default_factory=dict)
    use_llm: bool = True


# ---------------------------------------------------------------------------- overview
@router.get("/overview")
def get_overview(filters: dict = Depends(filters_dep), ctx: PlanningContext = Depends(ctx_dep)) -> dict[str, Any]:
    return overview(ctx, filters)


# ---------------------------------------------------------------------------- scenarios
@router.get("/scenarios")
def list_scenarios(ctx: PlanningContext = Depends(ctx_dep)) -> list[dict[str, Any]]:
    store.ensure_presets(ctx)
    return store.list_scenarios()


@router.post("/scenarios")
def create_scenario(req: ScenarioRequest) -> dict[str, Any]:
    return store.create_scenario(req.name, req.description, req.params)


@router.put("/scenarios/{scenario_id}")
def update_scenario(scenario_id: str, req: ScenarioRequest) -> dict[str, Any]:
    try:
        return store.update_scenario(scenario_id, req.name, req.description, req.params)
    except KeyError as exc:
        raise HTTPException(404, "Scenario not found") from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.delete("/scenarios/{scenario_id}")
def delete_scenario(scenario_id: str) -> dict[str, str]:
    try:
        store.delete_scenario(scenario_id)
    except KeyError as exc:
        raise HTTPException(404, "Scenario not found") from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    return {"deleted": scenario_id}


@router.post("/scenarios/{scenario_id}/duplicate")
def duplicate_scenario(scenario_id: str) -> dict[str, Any]:
    try:
        return store.duplicate_scenario(scenario_id)
    except KeyError as exc:
        raise HTTPException(404, "Scenario not found") from exc


@router.post("/scenarios/simulate")
def simulate_scenario(req: SimulateRequest, ctx: PlanningContext = Depends(ctx_dep)) -> dict[str, Any]:
    require_run(ctx)
    return simulate(ctx, ScenarioParams.from_dict(req.params), req.filters or None)


@router.get("/scenarios/compare")
def compare_scenarios(
    ids: list[str] | None = Query(None),
    measure: str = "revenue",
    filters: dict = Depends(filters_dep),
    ctx: PlanningContext = Depends(ctx_dep),
):
    require_run(ctx)
    store.ensure_presets(ctx)
    return store.compare(ctx, ids, filters, measure)


@router.get("/scenarios/elasticities")
def elasticities(ctx: PlanningContext = Depends(ctx_dep)) -> dict[str, Any]:
    from synthetic_data_generator.catalog import PRICE_ELASTICITY

    meta = clean(estimate_elasticities(ctx.version))
    return {
        "estimated": meta,
        "synthetic_truth": {
            "price_elasticity": PRICE_ELASTICITY,
            "distribution_elasticity": 0.9,
            "marketing_elasticity": 0.07,
        },
    }


# ---------------------------------------------------------------------------- S&OP
@router.get("/sop/cockpit")
def sop_cockpit(
    measure: str = Query("revenue", pattern="^(units|revenue)$"),
    filters: dict = Depends(filters_dep),
    ctx: PlanningContext = Depends(ctx_dep),
) -> dict[str, Any]:
    return cockpit(ctx, filters, measure)


@router.get("/sop/feasibility")
def sop_feasibility(
    months: list[str] | None = Query(None),
    measure: str = Query("revenue", pattern="^(units|revenue)$"),
    filters: dict = Depends(filters_dep),
    ctx: PlanningContext = Depends(ctx_dep),
) -> dict[str, Any]:
    require_run(ctx)
    a = assess(ctx, filters, months, measure)
    if a.get("available"):
        sigma = (a["p90"] - a["consensus"]) / 1.2815515655446004
        a["curve"] = probability_curve(a["consensus"], sigma)
        a["by_customer"] = feasibility_by(ctx, "customer", filters, measure)
    return a


@router.post("/sop/allocation")
def sop_allocation(req: AllocationRequest, ctx: PlanningContext = Depends(ctx_dep)) -> dict[str, Any]:
    require_run(ctx)
    try:
        return allocate(ctx, req.dimension, req.method, req.total_target, req.weights, req.filters, req.measure)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ---------------------------------------------------------------------------- FVA & alerts
@router.get("/fva")
def fva(filters: dict = Depends(filters_dep), ctx: PlanningContext = Depends(ctx_dep)) -> dict[str, Any]:
    return fva_report(ctx, filters)


@router.get("/alerts")
def alerts(
    severity: str | None = None, type: str | None = None, ctx: PlanningContext = Depends(ctx_dep)
) -> dict[str, Any]:
    items = build_alerts(ctx)
    out = [a for a in items if (not severity or a["severity"] == severity) and (not type or a["type"] == type)]
    return {"summary": summary(items), "alerts": out}


# ---------------------------------------------------------------------------- semantic & AI
@router.get("/semantic/catalog")
def semantic_catalog() -> dict[str, Any]:
    return catalog()


@router.get("/ai/status")
def ai_status(refresh: bool = False) -> dict[str, Any]:
    return llm.status(force=refresh)


@router.get("/ai/suggestions")
def ai_suggestions(lang: str = "en") -> list[str]:
    return analyst.SUGGESTIONS.get(lang, analyst.SUGGESTIONS["en"])


@router.post("/ai/ask")
def ai_ask(req: AskRequest, ctx: PlanningContext = Depends(ctx_dep)) -> dict[str, Any]:
    if not req.question.strip():
        raise HTTPException(400, "Question is empty")
    return analyst.ask(ctx, req.question[:500], req.filters, req.use_llm)
