"""Runtime configuration (environment variables with local-first defaults)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

APP_NAME = "ForecastLab"
APP_TAGLINE = "Planejamento de Demanda & S&OP com Inteligência de Decisão"
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


def _default_threads() -> int:
    cpus = os.cpu_count() or 4
    return max(2, min(8, round(cpus * 2 / 3)))


@dataclass(frozen=True)
class Settings:
    db_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("FORECASTLAB_DB_PATH", str(REPO_DIR / "database" / "forecastlab.duckdb"))
        )
    )
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"))
    # Empty = automatic choice among the pulled models (see app.ai.llm.PREFERRED_MODELS).
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "").strip())
    # Ceiling for one background narration (/api/ai/narrate); /api/ai/ask never waits for the LLM.
    ollama_timeout_s: float = field(default_factory=lambda: float(os.getenv("OLLAMA_TIMEOUT", "90")))
    # CPU threads for Ollama (0 = Ollama's default). Leaving ~1/3 of the cores free keeps the API
    # (deterministic answers in < 1,5 s) responsive while the local model writes a narration.
    ollama_num_thread: int = field(default_factory=lambda: int(os.getenv("OLLAMA_NUM_THREAD", str(_default_threads()))))
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
