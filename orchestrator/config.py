# orchestrator/config.py
import os
from pydantic_settings import BaseSettings
from pydantic import HttpUrl  # oppure: from pydantic import AnyUrl as HttpUrl



def _default_models_cfg_path() -> str:
    # <repo>/configs/models.yaml (risolve a partire da questo file)
    here = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(here, "..", "configs", "models.yaml"))

class Settings(BaseSettings):
    # Upstream Gateway
    GATEWAY_URL: HttpUrl = "http://localhost:8000"


    # Workspace & runs
    WORKSPACE_ROOT: str = os.getenv("WORKSPACE_ROOT", os.path.abspath(os.path.join(os.getcwd(), "..")))
    RUNS_DIR: str = os.getenv("RUNS_DIR", os.path.join(os.getcwd(), "runs"))

    # Timeouts & retries (LLM_TIMEOUT_S retro-compat)
    REQUEST_TIMEOUT_S: int = int(os.getenv("REQUEST_TIMEOUT_S", os.getenv("LLM_TIMEOUT_S", "60")))
    RETRY_MAX_ATTEMPTS: int = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
    RETRY_BACKOFF_S: float = float(os.getenv("RETRY_BACKOFF_S", "0.5"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # External services
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://ollama:11434")
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "qdrant")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))

    # Models config (fallback legacy, usato SOLO in fallback dal model_router)
    MODELS_CONFIG_PATH: str = os.getenv("MODELS_CONFIG", _default_models_cfg_path())

    # Tooling flags — unico posto per leggerli (retro-compat con ENV)
    def tool_flag(self, name: str, default: bool = True) -> bool:
        v = os.getenv(name, None)
        if v is None:
            return default
        return str(v).lower() in ("1", "true", "yes", "on")

    class Config:
        env_file = ".env"

settings = Settings()
