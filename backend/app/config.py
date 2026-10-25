"""Runtime configuration (environment variables with local-first defaults)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

APP_NAME = "ForecastLab"
APP_TAGLINE = "AI Demand Planning & S&OP Decision Intelligence"
APP_VERSION = "1.0.0"

AUTHOR = {
    "name": "Wallison Sampaio",
    "title_en": "Commercial Intelligence | Supply Chain | Data & AI Analytics Specialist",
    "title_pt": "Especialista em Inteligência Comercial | Supply Chain | Data & AI Analytics",
    "linkedin": "https://www.linkedin.com/in/wallisonsampaio",
    "signature_en": "Developed by Wallison Sampaio",
    "signature_pt": "Desenvolvido por Wallison Sampaio",
}


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    db_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("FORECASTLAB_DB_PATH", str(REPO_DIR / "database" / "forecastlab.duckdb"))
        )
    )
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3.2:3b"))
    ollama_timeout_s: float = field(default_factory=lambda: float(os.getenv("OLLAMA_TIMEOUT", "60")))
    ai_enabled: bool = field(default_factory=lambda: _bool("FORECASTLAB_AI_ENABLED", True))
    auto_bootstrap: bool = field(default_factory=lambda: _bool("FORECASTLAB_AUTO_BOOTSTRAP", True))
    demo_seed: int = field(default_factory=lambda: int(os.getenv("FORECASTLAB_DEMO_SEED", "42")))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            os.getenv("FORECASTLAB_CORS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173").split(
                ","
            )
        )
    )
    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("FORECASTLAB_MAX_UPLOAD_MB", "50")))


settings = Settings()
