"""ForecastLab API - AI Demand Planning & S&OP Decision Intelligence.

Developed by Wallison Sampaio
Commercial Intelligence | Supply Chain | Data & AI Analytics Specialist
https://www.linkedin.com/in/wallisonsampaio
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import db
from app.ai import llm
from app.api import data, deviations, export, forecast, journey, planning
from app.config import APP_NAME, APP_VERSION, AUTHOR, settings
from app.forecasting.models import model_catalog
from app.services import datasets, ptbr, runs
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
    description=f"{ptbr.APP_TAGLINE}. {AUTHOR['signature_pt']} · {AUTHOR['title_pt']}.",
    version=APP_VERSION,
    lifespan=lifespan,
    contact={"name": AUTHOR["name"], "url": AUTHOR["linkedin"]},
    license_info={"name": "MIT"},
)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(NoDatasetError)
async def no_dataset(_: Request, exc: NoDatasetError) -> JSONResponse:
    detail = str(exc) or "Nenhuma base ativa. Carregue um arquivo ou a base de demonstração."
    return JSONResponse(status_code=409, content={"detail": detail, "code": "no_dataset"})


# Portuguese text for the framework's default error details (unknown route, wrong method ...).
DEFAULT_ERROR_DETAIL = {
    400: "Requisição inválida.",
    401: "Autenticação necessária.",
    403: "Acesso negado.",
    404: "Recurso não encontrado.",
    405: "Método não permitido para este endpoint.",
    413: "Conteúdo maior que o limite permitido.",
    415: "Tipo de conteúdo não suportado.",
    500: "Erro interno do servidor.",
}


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    """Keep the endpoints' own (Portuguese) details; translate the framework's default English phrases."""
    try:
        default = HTTPStatus(exc.status_code).phrase
    except ValueError:
        default = None
    if exc.status_code in DEFAULT_ERROR_DETAIL and exc.detail in (None, "", default):
        exc = StarletteHTTPException(exc.status_code, DEFAULT_ERROR_DETAIL[exc.status_code], headers=exc.headers)
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Portuguese message for malformed requests (the raw pydantic errors stay under "errors")."""
    fields = sorted({".".join(str(p) for p in e.get("loc", ())[1:]) or "corpo" for e in exc.errors()})
    return JSONResponse(
        status_code=422,
        content={
            "detail": f"Requisição inválida. Verifique o(s) campo(s): {', '.join(fields)}.",
            "errors": jsonable_encoder(exc.errors()),
        },
    )


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
        "tagline": ptbr.APP_TAGLINE,
        "version": APP_VERSION,
        "author": {
            "name": AUTHOR["name"],
            "title": AUTHOR["title_pt"],
            "signature": AUTHOR["signature_pt"],
            "linkedin": AUTHOR["linkedin"],
        },
        "models": ptbr.model_catalog(model_catalog()),
        "horizons": [3, 6, 12, 18, 24],
        "ai": llm.status(max_wait=0.5),  # never hold the first page load on a slow Ollama
        "database": "DuckDB",
    }


for r in (data.router, forecast.router, planning.router, export.router, deviations.router, journey.router):
    app.include_router(r)
