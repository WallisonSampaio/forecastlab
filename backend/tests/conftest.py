from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("FORECASTLAB_AUTO_BOOTSTRAP", "false")
os.environ.setdefault("FORECASTLAB_AI_ENABLED", "false")
os.environ.setdefault("FORECASTLAB_WORKERS", "1")
os.environ.setdefault("FORECASTLAB_DB_PATH", ":memory:")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from synthetic_data_generator import generate_dataset

FAST_MODELS = ["Naive", "Seasonal Naive", "Moving Average", "SES", "Holt", "Croston", "SBA", "TSB", "Regression"]


@pytest.fixture(scope="session")
def demo():
    return generate_dataset(random_seed=7)


@pytest.fixture(scope="session")
def small_sales(demo) -> pd.DataFrame:
    """Two customers of the synthetic dataset, in the upload (display) format."""
    keep = demo.sales["Customer"].isin(["Vila Verde Mercados", "CuraMais Farmácias"])
    return demo.sales[keep].reset_index(drop=True)


@pytest.fixture
def seasonal_series() -> np.ndarray:
    rng = np.random.default_rng(0)
    t = np.arange(60)
    return 1000 * (1 + 0.35 * np.sin(2 * np.pi * t / 12)) * (1.006**t) * np.exp(rng.normal(0, 0.05, 60))


@pytest.fixture(scope="session")
def api_client(small_sales, tmp_path_factory):
    """FastAPI TestClient on an isolated DuckDB file with a completed forecast run."""
    from fastapi.testclient import TestClient

    from app import db
    from app.forecasting.worker import RunParams
    from app.main import app
    from app.services import datasets, runs
    from app.validation.health import validate_and_normalize

    db.connect(tmp_path_factory.mktemp("db") / "test.duckdb")
    report, norm = validate_and_normalize(small_sales)
    assert norm is not None
    version = datasets.store_dataset(norm, report, name="test", source="test", file_name="test.csv")
    runs.start_run(RunParams(models=FAST_MODELS), dataset_version=version, wait=True, workers=1)
    with TestClient(app) as client:
        yield client
