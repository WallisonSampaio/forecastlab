"""Data endpoints: upload, validation, datasets, template, exploration."""

from __future__ import annotations

import io
import logging
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.ingestion.readers import SUPPORTED, UnsupportedFileError, read_table, unsupported_message
from app.ingestion.schema import PLAN_REQUIRED, is_plan_sheet, map_plan_columns
from app.ingestion.template import build_template
from app.services import datasets, runs
from app.services.context import NoDatasetError, PlanningContext, clean, filter_ids, get_context, records
from app.services.eda import demand_overview, series_profiles
from app.validation.health import score_label, validate_and_normalize

from .deps import ctx_dep, filters_dep

router = APIRouter(prefix="/api/data", tags=["data"])
log = logging.getLogger("forecastlab.data")


class DemoRequest(BaseModel):
    seed: int = 42
    run_forecast: bool = True


READ_ERROR = "Não foi possível ler o arquivo. Verifique se ele não está corrompido ou protegido por senha."


def _plan_columns(columns: list[Any]) -> dict[str, Any]:
    """canonical plan field -> original column name (PT/EN headers, case- and accent-insensitive)."""
    return map_plan_columns(columns)


def _recent_price(sales: pd.DataFrame) -> pd.Series:
    """(customer, sku) -> revenue / units over each series' last 6 months (the derived plan's price rule)."""
    if not {"date", "units", "revenue"} <= set(sales.columns):
        return pd.Series(dtype=float)
    last6 = sales.sort_values("date").groupby(["customer", "sku"]).tail(6)
    totals = last6.groupby(["customer", "sku"])[["revenue", "units"]].sum(min_count=1)
    return totals["revenue"] / totals["units"].where(totals["units"] > 0)


def _read_plan(content: bytes, file_name: str, sales: pd.DataFrame) -> pd.DataFrame | None:
    """Optional plan sheet inside an uploaded workbook.

    The sheet name is matched case- and accent-insensitively ("Plano (opcional)", "Plano", "Orçamento", "Plan",
    "Plan (optional)", "Budget", "Meta"…), and the columns by their PT/EN aliases ("Orçamento (unidades)",
    "OrçamentoUnidades", "BudgetUnits", "Meta (unidades)"…). Names are trimmed like the data sheet, values are
    read as numbers, and rows without a valid month, without budget and target units, or of unknown
    Cliente x SKU pairs are dropped. Returns None when no row is left (the plan is then derived).

    Budget/target revenue left blank is filled with units x the series' recent price (revenue / units over its
    last 6 months, as in ``datasets.derive_plan``): the report and the deviation analysis compare in R$.
    """
    if not file_name.lower().endswith((".xlsx", ".xls")):
        return None
    xl = pd.ExcelFile(io.BytesIO(content))
    df, cols = None, {}
    for sheet in (s for s in xl.sheet_names if is_plan_sheet(s)):
        candidate = pd.read_excel(xl, sheet_name=sheet)
        cols = _plan_columns(list(candidate.columns))
        if all(k in cols for k in PLAN_REQUIRED):
            df = candidate
            break
    if df is None:
        return None
    out = pd.DataFrame({k: df[cols[k]] for k in PLAN_REQUIRED})
    out["budget_revenue"] = df[cols["budget_revenue"]] if "budget_revenue" in cols else None
    out["target_revenue"] = df[cols["target_revenue"]] if "target_revenue" in cols else None
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    for c in ("customer", "sku"):
        out[c] = out[c].astype(str).str.strip()
    for c in ("budget_units", "target_units", "budget_revenue", "target_revenue"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    keys = set(zip(sales["customer"].astype(str), sales["sku"].astype(str), strict=True))
    out = out[[(c, s) in keys for c, s in zip(out["customer"], out["sku"], strict=True)]]
    out = out.dropna(subset=["date"]).dropna(subset=["budget_units", "target_units"], how="all")
    if not len(out):
        return None
    out = out.reset_index(drop=True)
    price = _recent_price(sales).reindex(pd.MultiIndex.from_arrays([out["customer"], out["sku"]])).to_numpy()
    for units, revenue in (("budget_units", "budget_revenue"), ("target_units", "target_revenue")):
        out[revenue] = out[revenue].fillna(out[units] * price)
    return out


@router.post("/upload")
async def upload(file: UploadFile = File(...), run_forecast: bool = Query(True)) -> dict[str, Any]:
    name = file.filename or "arquivo"
    if not name.lower().endswith(SUPPORTED):
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else None
        raise HTTPException(400, unsupported_message(f".{ext}" if ext else None))
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Arquivo maior que o limite de {settings.max_upload_mb} MB.")
    try:
        raw = read_table(content, name)
    except UnsupportedFileError as exc:  # pt-BR messages written by ingestion.readers
        raise HTTPException(400, str(exc) or unsupported_message()) from exc
    except Exception as exc:
        log.warning("Could not read uploaded file %s: %s", name, exc)
        raise HTTPException(400, READ_ERROR) from exc
    report, norm = validate_and_normalize(raw)
    out: dict[str, Any] = {
        "file_name": name,
        "validation": report.to_dict(),
        "quality_label": score_label(report.quality["overall"]),
    }
    if norm is None:
        out.update(accepted=False, dataset_version=None, run_id=None)
        return clean(out)
    try:
        plan = _read_plan(content, name, norm)
    except Exception as exc:  # a malformed plan sheet must not block a valid sales sheet
        log.warning("Could not read the plan sheet of %s: %s", name, exc)
        plan = None
    version = datasets.store_dataset(
        norm,
        report,
        name=name.rsplit(".", 1)[0],
        source="upload",
        file_name=name,
        plan=plan,
        plan_source=datasets.UPLOADED_PLAN_SHEET_SOURCE if plan is not None else None,
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
        raise HTTPException(409, "Há uma execução de forecast em andamento; aguarde a conclusão.")
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
        raise HTTPException(404, "Nenhuma base ativa")
    ds = datasets.get_dataset(version)
    if ds is None:
        raise HTTPException(404, "Base ativa não encontrada")
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
        raise HTTPException(404, "Base não encontrada")
    if ds["status"] == "blocked":
        raise HTTPException(409, "A base tem erros críticos de validação e não pode ser ativada")
    datasets.activate(version)
    return {"dataset_version": version, "active_run": runs.latest_successful_run(version)}


@router.get("/template")
def template() -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(build_template()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="forecastlab_modelo_de_planilha.xlsx"'},
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
