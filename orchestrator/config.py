# orchestrator/config.py
"""Single source of orchestrator configuration (WP7.11).

Values come from the environment (or ``.env``) and are typed and validated by pydantic-settings.
Paths that tests and containers override at runtime (``RUNS_DIR``) are resolved through helper
functions at call time, with one default.
"""

import os
from pathlib import Path

from pydantic import AliasChoices, Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Upstream services
    GATEWAY_URL: HttpUrl = "http://localhost:8000"
    OLLAMA_URL: str = "http://ollama:11434"
    EMBED_MODEL: str = "nomic-embed-text"
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333

    # Timeouts (LLM_TIMEOUT_S kept as a legacy alias)
    REQUEST_TIMEOUT_S: int = Field(240, validation_alias=AliasChoices("REQUEST_TIMEOUT_S", "LLM_TIMEOUT_S"))

    # Workspace layout for code generation
    WORKSPACE_ROOT: str = Field(default_factory=lambda: os.path.abspath(os.path.join(os.getcwd(), "..")))
    CODE_ROOT: str = "src"
    CODE_ROOT_BASE: str = "src"
    TEST_ROOT_BASE: str = "tests"
    GEN_ID_PREFIX: str = "generated"

    @property
    def RUNS_DIR(self) -> str:  # noqa: N802 - kept for existing callers
        return str(runs_dir())


def runs_dir() -> Path:
    """Directory for run artifacts (``RUNS_DIR``; ``/app/runs`` in containers)."""
    return Path(os.getenv("RUNS_DIR") or os.path.join(os.getcwd(), "runs")).resolve()


settings = Settings()
