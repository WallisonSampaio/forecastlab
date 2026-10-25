"""ForecastLab API - AI Demand Planning & S&OP Decision Intelligence.

Developed by Wallison Sampaio
Commercial Intelligence | Supply Chain | Data & AI Analytics Specialist
https://www.linkedin.com/in/wallisonsampaio
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import db
from app.ai import llm
from app.api import data, export, forecast, planning
from app.config import APP_NAME, APP_TAGLINE, APP_VERSION, AUTHOR, settings
from app.forecasting.models import model_catalog
from app.services import datasets, runs
from app.services.context import NoDatasetError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("forecastlab")


def bootstrap() -> None:
    """First start: load the synthetic demo dataset and run the first forecast."""
    if db.scalar("SELECT COUNT(*) FROM datasets"):
        try:  # keep preset scenarios aligned with the current horizon and definitions
            from app.scenarios.store import ensure_presets, refresh_presets
            from app.services.context import get_context

            ctx = get_context()
            if ctx.has_run:
                ensure_presets(ctx)
                refresh_presets(ctx)
        except Exception:
            log.exception("Preset refresh skipped")
        return
    log.info("Empty database - loading synthetic demo dataset (seed %s)", settings.demo_seed)
    version = datasets.load_demo_dataset(settings.demo_seed)
    runs.start_run(dataset_version=version)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.get_conn()  # opens the database unless a connection already exists (tests)
    if settings.auto_bootstrap:
        threading.Thread(target=bootstrap, daemon=True, name="bootstrap").start()
    yield


app = FastAPI(
    title=f"{APP_NAME} API",
    description=f"{APP_TAGLINE}. {AUTHOR['signature_en']} — {AUTHOR['title_en']}.",
    version=APP_VERSION,
    lifespan=lifespan,
    contact={"name": AUTHOR["name"], "url": AUTHOR["linkedin"]},
    license_info={"name": "MIT"},
)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(NoDatasetError)
async def no_dataset(_: Request, exc: NoDatasetError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc), "code": "no_dataset"})


@app.get("/api/health", tags=["system"])
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "app": APP_NAME,
        "version": APP_VERSION,
        "dataset": datasets.active_version(),
        "job": (runs.current_job() or {}).get("status"),
    }


@app.get("/api/meta", tags=["system"])
def meta() -> dict[str, Any]:
    return {
        "app": APP_NAME,
        "tagline": APP_TAGLINE,
        "version": APP_VERSION,
        "author": AUTHOR,
        "models": model_catalog(),
        "horizons": [3, 6, 12, 18, 24],
        "ai": llm.status(),
        "database": "DuckDB",
        "db_path": str(settings.db_path),
    }


for r in (data.router, forecast.router, planning.router, export.router):
    app.include_router(r)
