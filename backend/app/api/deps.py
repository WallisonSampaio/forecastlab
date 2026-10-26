"""Shared API dependencies: hierarchy filters and the planning context."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query

from app.services.context import PlanningContext, get_context


def filters_dep(
    region: list[str] | None = Query(None),
    channel: list[str] | None = Query(None),
    customer: list[str] | None = Query(None),
    category: list[str] | None = Query(None),
    brand: list[str] | None = Query(None),
    sku: list[str] | None = Query(None),
) -> dict[str, Any]:
    raw = {"region": region, "channel": channel, "customer": customer, "category": category, "brand": brand, "sku": sku}
    return {k: v for k, v in raw.items() if v}


def ctx_dep() -> PlanningContext:
    return get_context()


def require_run(ctx: PlanningContext) -> PlanningContext:
    if not ctx.has_run:
        raise HTTPException(
            status_code=409, detail="Ainda não há uma execução de forecast concluída. Execute o forecast primeiro."
        )
    return ctx


def measure_param(measure: str = Query("units", pattern="^(units|revenue)$")) -> str:
    return measure
