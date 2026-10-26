"""Entry point of the deep dive: validates the request and dispatches on ``cmp``.

fc_pl / fc_tg / ac_pl -> ``plan``; ac_fc / ac_cs -> ``forecast_error`` (spec §4.3.3).
Invalid cmp / level / measure raise ``common.DeviationError`` (HTTP 400 with a pt-BR detail);
the period is validated by the engines with ``common.parse_period``.
"""

from __future__ import annotations

from types import ModuleType
from typing import Any

from app.services.context import PlanningContext

from . import common, forecast_error, plan


def _engine(cmp: str) -> ModuleType:
    return plan if common.lens_of(cmp) == "plan" else forecast_error


def _focus_level(cmp: str, focus_level: str | None, focus: str | None, level: str | None) -> str | None:
    """Validated focus level. Without ``focus_level``, a focused member belongs to the breakdown
    ``level`` (the frontend sends ``level`` with every call); the engines then fall back to
    ``next_level(filters)``."""
    focus_level = common.validate_level(cmp, focus_level)
    level = common.validate_level(cmp, level)
    if focus_level is None and focus not in (None, ""):
        return level
    return focus_level


def summary(
    ctx: PlanningContext,
    filters: dict[str, Any],
    cmp: str,
    period: str | None = None,
    measure: str = "revenue",
    level: str | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    engine = _engine(cmp)
    measure = common.validate_measure(cmp, measure)
    level = common.validate_level(cmp, level) or common.next_level(filters)
    return engine.summary(ctx, filters, cmp, period, measure, level, limit)


def focus(
    ctx: PlanningContext,
    filters: dict[str, Any],
    cmp: str,
    period: str | None = None,
    measure: str = "revenue",
    focus_level: str | None = None,
    focus: str | None = None,
    level: str | None = None,
) -> dict[str, Any]:
    engine = _engine(cmp)
    measure = common.validate_measure(cmp, measure)
    focus_level = _focus_level(cmp, focus_level, focus, level)
    return engine.focus(ctx, filters, cmp, period, measure, focus_level, focus)


def exceptions(
    ctx: PlanningContext,
    filters: dict[str, Any],
    cmp: str,
    period: str | None = None,
    measure: str = "revenue",
    focus_level: str | None = None,
    focus: str | None = None,
    direction: str = "adverse",
    cause: str | None = None,
    limit: int = 15,
    offset: int = 0,
    level: str | None = None,
) -> dict[str, Any]:
    """``direction`` (adverse | favorable | all) applies to the plan lens, ``cause`` to the forecast lens."""
    engine = _engine(cmp)
    measure = common.validate_measure(cmp, measure)
    focus_level = _focus_level(cmp, focus_level, focus, level)
    if engine is plan:
        if direction not in ("adverse", "favorable", "all"):
            raise common.DeviationError(common.MSG_INVALID_DIRECTION)
        return plan.exceptions(ctx, filters, cmp, period, measure, focus_level, focus, direction, limit, offset)
    return forecast_error.exceptions(ctx, filters, cmp, period, measure, focus_level, focus, cause, limit, offset)


def series(
    ctx: PlanningContext, series_id: str, cmp: str, period: str | None = None, measure: str = "revenue"
) -> dict[str, Any]:
    engine = _engine(cmp)
    measure = common.validate_measure(cmp, measure)
    common.require_series(ctx, series_id)
    return engine.series(ctx, series_id, cmp, period, measure)
