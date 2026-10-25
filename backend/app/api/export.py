"""Exports: Excel planning workbook, executive Excel and executive HTML."""

from __future__ import annotations

import io
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, StreamingResponse

from app.exports.excel import build_executive_workbook, build_workbook
from app.exports.html_report import build_html
from app.services.context import PlanningContext

from .deps import ctx_dep, filters_dep, require_run

router = APIRouter(prefix="/api/export", tags=["export"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(content: bytes, name: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(content), media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'}
    )


@router.get("/excel")
def excel(
    scenario_id: str | None = None, filters: dict = Depends(filters_dep), ctx: PlanningContext = Depends(ctx_dep)
) -> StreamingResponse:
    require_run(ctx)
    return _xlsx(build_workbook(ctx, filters, scenario_id), f"forecastlab_plan_{datetime.now():%Y%m%d_%H%M}.xlsx")


@router.get("/executive-excel")
def executive_excel(filters: dict = Depends(filters_dep), ctx: PlanningContext = Depends(ctx_dep)):
    require_run(ctx)
    return _xlsx(build_executive_workbook(ctx, filters), f"forecastlab_executive_{datetime.now():%Y%m%d}.xlsx")


@router.get("/executive-html", response_class=HTMLResponse)
def executive_html(
    download: bool = False, filters: dict = Depends(filters_dep), ctx: PlanningContext = Depends(ctx_dep)
) -> HTMLResponse:
    require_run(ctx)
    headers = (
        {"Content-Disposition": f'attachment; filename="forecastlab_executive_{datetime.now():%Y%m%d}.html"'}
        if download
        else None
    )
    return HTMLResponse(build_html(ctx, filters), headers=headers)
