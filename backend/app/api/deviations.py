"""Deviation deep-dive endpoints: /api/deviations/{summary,focus,exceptions,series} (spec §4.3.3).

All endpoints are GET, accept the hierarchy filters, return JSON-safe values (``clean``) and answer
invalid input with HTTP 400 (404 for an unknown series) and a pt-BR ``detail``. Capability gaps
(no plan rows, no historical adjustments) are HTTP 200 with ``available: false`` and a ``reason``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deviations import service
from app.deviations.common import DeviationError
from app.services.context import PlanningContext, clean

from .deps import ctx_dep, filters_dep, require_run

router = APIRouter(prefix="/api", tags=["deviations"])


def _run(fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return clean(fn())
    except DeviationError as exc:
        raise HTTPException(exc.status, exc.message) from exc


@router.get("/deviations/summary")
def deviations_summary(
    cmp: str = Query(..., description="fc_pl | fc_tg | ac_pl | ac_fc | ac_cs"),
    period: str | None = Query(None, description="h | t1..t4 | u12m | bt | YYYY-MM"),
    measure: str | None = Query(None, description="revenue | units (default revenue)"),
    level: str | None = Query(None),
    limit: int = Query(12, ge=1, le=100),
    filters: dict = Depends(filters_dep),
    ctx: PlanningContext = Depends(ctx_dep),
) -> dict[str, Any]:
    require_run(ctx)
    return _run(lambda: service.summary(ctx, filters, cmp, period, measure, level, limit))


@router.get("/deviations/focus")
def deviations_focus(
    cmp: str = Query(...),
    period: str | None = Query(None),
    measure: str | None = Query(None),
    focus_level: str | None = Query(None),
    focus: str | None = Query(None),
    level: str | None = Query(None, description="breakdown level; focus level when focus_level is omitted"),
    filters: dict = Depends(filters_dep),
    ctx: PlanningContext = Depends(ctx_dep),
) -> dict[str, Any]:
    require_run(ctx)
    return _run(lambda: service.focus(ctx, filters, cmp, period, measure, focus_level, focus, level))


@router.get("/deviations/exceptions")
def deviations_exceptions(
    cmp: str = Query(...),
    period: str | None = Query(None),
    measure: str | None = Query(None),
    focus_level: str | None = Query(None),
    focus: str | None = Query(None),
    direction: str = Query("adverse", description="adverse | favorable | all (plan lens)"),
    cause: str | None = Query(None, description="cause code (forecast lens)"),
    limit: int = Query(15, ge=1, le=200),
    offset: int = Query(0, ge=0),
    level: str | None = Query(None, description="breakdown level; focus level when focus_level is omitted"),
    filters: dict = Depends(filters_dep),
    ctx: PlanningContext = Depends(ctx_dep),
) -> dict[str, Any]:
    require_run(ctx)
    return _run(
        lambda: service.exceptions(
            ctx, filters, cmp, period, measure, focus_level, focus, direction, cause, limit, offset, level
        )
    )


@router.get("/deviations/series")
def deviations_series(
    series_id: str = Query(...),
    cmp: str = Query(...),
    period: str | None = Query(None),
    measure: str | None = Query(None),
    ctx: PlanningContext = Depends(ctx_dep),
) -> dict[str, Any]:
    require_run(ctx)
    return _run(lambda: service.series(ctx, series_id, cmp, period, measure))
