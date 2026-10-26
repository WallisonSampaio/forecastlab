"""Journey endpoints: /api/journey, /api/models/trust and /api/story (spec §4.3.1, §4.3.2, §4.5).

* ``/api/journey`` always answers HTTP 200, even without a dataset (stage "dados").
* ``/api/models/trust`` and ``/api/story`` answer ``{available: false, reason}`` (HTTP 200) without a
  completed run; with a run they are cached per context (and per filters for the story).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.services import trust as trust_service
from app.services.context import PlanningContext, clean
from app.story.builder import build_story

from .deps import ctx_dep, filters_dep

router = APIRouter(prefix="/api", tags=["journey"])


@router.get("/journey")
def journey() -> dict[str, Any]:
    """Stage of the journey (dados | modelos | pronto), active dataset and run state."""
    return clean(trust_service.journey_status())


@router.get("/models/trust")
def models_trust(ctx: PlanningContext = Depends(ctx_dep)) -> dict[str, Any]:
    """How much the forecast deserves credit: accuracy, wins per model, confidence and verdict."""
    return clean(trust_service.trust(ctx))


@router.get("/story")
def story(filters: dict = Depends(filters_dep), ctx: PlanningContext = Depends(ctx_dep)) -> dict[str, Any]:
    """The 7-chapter executive report (revenue), for the company or one scope member."""
    return clean(build_story(ctx, filters))
