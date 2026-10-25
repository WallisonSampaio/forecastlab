"""Data endpoints: upload, validation, datasets, template, exploration."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.ingestion.readers import SUPPORTED, UnsupportedFileError, read_table
from app.ingestion.schema import normalize_key
from app.ingestion.template import build_template
from app.services import datasets, runs
from app.services.context import NoDatasetError, PlanningContext, clean, filter_ids, get_context, records
from app.services.eda import demand_overview, series_profiles
from app.validation.health import score_label, validate_and_normalize

from .deps import ctx_dep, filters_dep

router = APIRouter(prefix="/api/data", tags=["data"])


class DemoRequest(BaseModel):
    seed: int = 42
    run_forecast: bool = True


def _read_plan(content: bytes, file_name: str, sales: pd.DataFrame) -> pd.DataFrame | None:
    """Optional plan sheet ("Plan...") inside an uploaded workbook."""
    if not file_name.lower().endswith((".xlsx", ".xls")):
        return None
    xl = pd.ExcelFile(io.BytesIO(content))
    sheet = next((s for s in xl.sheet_names if s.lower().startswith(("plan", "budget", "orcamento"))), None)
    if not sheet:
        return None
    df = xl.parse(sheet)
    cols = {normalize_key(c): c for c in df.columns}
    need = {
        "date": "date",
        "customer": "customer",
        "sku": "sku",
        "budgetunits": "budget_units",
        "targetunits": "target_units",
    }
    if not all(k in cols for k in need):
        return None
    out = pd.DataFrame({v: df[cols[k]] for k, v in need.items()})
    out["budget_revenue"] = df[cols["budgetrevenue"]] if "budgetrevenue" in cols else None
    out["target_revenue"] = df[cols["targetrevenue"]] if "targetrevenue" in cols else None
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    keys = set(zip(sales["customer"], sales["sku"], strict=True))
    out = out[[(c, s) in keys for c, s in zip(out["customer"].astype(str), out["sku"].astype(str), strict=True)]]
    return out.dropna(subset=["date"]) if len(out) else None


@router.post("/upload")
async def upload(file: UploadFile = File(...), run_forecast: bool = Query(True)) -> dict[str, Any]:
    name = file.filename or "upload"
    if not name.lower().endswith(SUPPORTED):
        raise HTTPException(400, f"Unsupported file type. Use one of: {', '.join(SUPPORTED)}")
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File larger than {settings.max_upload_mb} MB")
    try:
        raw = read_table(content, name)
    except UnsupportedFileError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Could not read the file: {exc}") from exc
    report, norm = validate_and_normalize(raw)
    out: dict[str, Any] = {
        "file_name": name,
        "validation": report.to_dict(),
        "quality_label": score_label(report.quality["overall"]),
    }
    if norm is None:
        out.update(accepted=False, dataset_version=None, run_id=None)
        return clean(out)
    plan = _read_plan(content, name, norm)
    version = datasets.store_dataset(
        norm,
        report,
        name=name.rsplit(".", 1)[0],
        source="upload",
        file_name=name,
        plan=plan,
        plan_source="Uploaded plan sheet" if plan is not None else None,
    )
    out.update(accepted=True, dataset_version=version, run_id=None)
    if run_forecast:
        try:
            out["run_id"] = runs.start_run(dataset_version=version)
        except runs.RunBlockedError as exc:
            out["run_message"] = str(exc)
    return clean(out)


@router.post("/demo")
def load_demo(req: DemoRequest) -> dict[str, Any]:
    if runs.current_job():
        raise HTTPException(409, "A forecast run is in progress; wait for it to finish.")
    version = datasets.load_demo_dataset(req.seed)
    run_id = runs.start_run(dataset_version=version) if req.run_forecast else None
    return {"dataset_version": version, "run_id": run_id}


@router.get("/datasets")
def list_all() -> list[dict[str, Any]]:
    return records(datasets.list_datasets())


@router.get("/active")
def active() -> dict[str, Any]:
    version = datasets.active_version()
    if not version:
        raise HTTPException(404, "No active dataset")
    ds = datasets.get_dataset(version)
    if ds is None:
        raise HTTPException(404, "Active dataset not found")
    ds["quality_label"] = score_label(ds.get("quality_score"))
    ds["active_run"] = None
    try:
        ds["active_run"] = get_context().run_id
    except NoDatasetError:
        pass
    return clean(ds)


@router.post("/datasets/{version}/activate")
def activate(version: str) -> dict[str, Any]:
    ds = datasets.get_dataset(version)
    if ds is None:
        raise HTTPException(404, "Dataset not found")
    if ds["status"] == "blocked":
        raise HTTPException(409, "Dataset has critical validation errors")
    datasets.activate(version)
    return {"dataset_version": version, "active_run": runs.latest_successful_run(version)}


@router.get("/template")
def template() -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(build_template()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="forecastlab_upload_template.xlsx"'},
    )


@router.get("/preview")
def preview(
    limit: int = Query(200, le=2000),
    offset: int = 0,
    filters: dict = Depends(filters_dep),
    ctx: PlanningContext = Depends(ctx_dep),
) -> dict[str, Any]:
    ids = filter_ids(ctx, filters)
    sales = datasets.get_sales(ctx.version)
    sales = sales[(sales["customer"] + "|" + sales["sku"]).isin(ids)].drop(columns=["dataset_version"])
    sales = sales.sort_values(["date", "customer", "sku"], ascending=[False, True, True])
    return {"total": len(sales), "rows": records(sales.iloc[offset : offset + limit])}


@router.get("/dimensions")
def dimensions(ctx: PlanningContext = Depends(ctx_dep)) -> dict[str, Any]:
    s = ctx.series
    return {
        "region": sorted(s["region"].dropna().unique().tolist()),
        "channel": sorted(s["channel"].dropna().unique().tolist()),
        "customer": sorted(s["customer"].dropna().unique().tolist()),
        "category": sorted(s["category"].dropna().unique().tolist()),
        "brand": sorted(s["brand"].dropna().unique().tolist()),
        "sku": records(s[["sku", "product", "category", "brand"]].drop_duplicates().sort_values("sku")),
        "customers": records(
            s[["customer", "region", "channel", "customer_location"]].drop_duplicates().sort_values("customer")
        ),
        "series": records(s[["series_id", "customer", "sku", "product"]].sort_values(["customer", "sku"])),
        "last_actual": ctx.last_actual.strftime("%Y-%m-%d"),
        "horizon": [d.strftime("%Y-%m-%d") for d in ctx.future_dates],
    }


@router.get("/eda")
def eda(
    measure: str = Query("units", pattern="^(units|revenue)$"),
    filters: dict = Depends(filters_dep),
    ctx: PlanningContext = Depends(ctx_dep),
) -> dict[str, Any]:
    return demand_overview(ctx, filters, measure)


@router.get("/profiles")
def profiles(filters: dict = Depends(filters_dep), ctx: PlanningContext = Depends(ctx_dep)) -> dict[str, Any]:
    return series_profiles(ctx, filters)
