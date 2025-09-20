# orchestrator/config.py
import os
from pydantic_settings import BaseSettings
from pydantic import HttpUrl  # oppure: from pydantic import AnyUrl as HttpUrl


def _get_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.lower() in {"1","true","yes","on"}


def _default_models_cfg_path() -> str:
    # <repo>/configs/models.yaml (risolve a partire da questo file)
    here = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(here, "..", "configs", "models.yaml"))

class Settings(BaseSettings):
    # Upstream Gateway
    GATEWAY_URL: HttpUrl = os.getenv("GATEWAY_URL", "http://localhost:8000")
    EMBED_MODEL: str = os.getenv("EMBED_MODEL", "nomic-embed-text")
    PREFER_LOCAL_FOR_CODEGEN: str = os.getenv("PREFER_LOCAL_FOR_CODEGEN", "true")
    PREFER_FRONTIER_FOR_REASONING: str = os.getenv("PREFER_FRONTIER_FOR_REASONING", "true")
    NEVER_SEND_SOURCE_TO_CLOUD: str = os.getenv("NEVER_SEND_SOURCE_TO_CLOUD", "true")
    OPTIMIZE_FOR: str = os.getenv("OPTIMIZE_FOR", "capability")

    CODE_ROOT_BASE: str = "src"
    TEST_ROOT_BASE: str = "tests"
    GEN_ID_PREFIX: str = "generated"
    ENSURE_MIN_TESTS: bool = True
    SPLIT_DEFAULT_STRATEGY: str = "per_symbol"
# Workspace & runs
    WORKSPACE_ROOT: str = os.getenv("WORKSPACE_ROOT", os.path.abspath(os.path.join(os.getcwd(), "..")))
    RUNS_DIR: str = os.getenv("RUNS_DIR", os.path.join(os.getcwd(), "runs"))

    # Timeouts & retries (LLM_TIMEOUT_S retro-compat)
    REQUEST_TIMEOUT_S: int = int(os.getenv("REQUEST_TIMEOUT_S", os.getenv("LLM_TIMEOUT_S", "240")))
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
    MODELS_CONFIG: str = os.getenv("MODELS_CONFIG", _default_models_cfg_path())


    # --- Feature flags split multi-lingua (fase 1: anche solo segnaposto) ---
    SPLIT_ENABLE_PY: bool = True
    SPLIT_ENABLE_TS: bool = True     # vale anche per Node/JS in fase 1
    SPLIT_ENABLE_GO: bool = True
    SPLIT_ENABLE_JAVA: bool = True
    SPLIT_ENABLE_REACT: bool = True
    SPLIT_ENABLE_MENDIX: bool = False  # Mendix gestito prudenzialmente (doc/template)

    # --- Policy test minimi ---
    ENSURE_MIN_TESTS: bool = True

    # --- Prefisso per gli id di generazione ---
    GEN_ID_PREFIX: str = "generated"
    SPLIT_DEFAULT_STRATEGY: str = "per_symbol"  # "none" | "per_symbol" | "per_filehint"

    # --- Tests scaffold policy ---
    TEST_POLICY_DEFAULT: str = "ensure_min_tests"  # "none" | "ensure_min_tests"

    # --- Paths di progetto (usati per mapping file e test) ---
    CODE_ROOT: str = "src"
    TEST_ROOT: str = "tests"


    # Tooling flags — unico posto per leggerli (retro-compat con ENV)
    def tool_flag(self, name: str, default: bool = True) -> bool:
        v = os.getenv(name, None)
        if v is None:
            return default
        return str(v).lower() in ("1", "true", "yes", "on")

    class Config:
        env_file = ".env"


settings = Settings()
