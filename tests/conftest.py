# Pytest fixtures to load the orchestrator using your local ./configs/models_test.yaml
# and to provide a TestClient for API tests.

import os
import sys
import importlib
from pathlib import Path
import pytest

MODELS_LOCAL_PATH = Path("./configs/models_test.yaml")

def _reload_with_local_models(extra_env: dict | None = None):
    if not MODELS_LOCAL_PATH.exists():
        raise FileNotFoundError(f"Missing {MODELS_LOCAL_PATH}. Please create it before running tests.")

    # Point orchestrator to your local config
    os.environ["MODELS_CONFIG"] = str(MODELS_LOCAL_PATH.resolve())

    # Default toggles (you can override per-test via monkeypatch)
    os.environ["PREFER_LOCAL_FOR_CODEGEN"] = "true"
    os.environ["PREFER_FRONTIER_FOR_REASONING"] = "true"
    os.environ["NEVER_SEND_SOURCE_TO_CLOUD"] = "true"
    os.environ["OPTIMIZE_FOR"] = "capability"

    if extra_env:
        for k, v in extra_env.items():
            os.environ[k] = v

    # Hard-reload orchestrator modules in a clean order
    for m in [
        "orchestrator.app",
        "orchestrator.routes.harper",
        "orchestrator.services.router",
        "orchestrator.config",
    ]:
        if m in sys.modules:
            del sys.modules[m]

    import orchestrator.config as cfg
    import orchestrator.services.router as router
    import orchestrator.routes.harper as routes
    import orchestrator.app as app

    importlib.reload(cfg)
    importlib.reload(router)
    importlib.reload(routes)
    importlib.reload(app)

    return router, app.app  # router module and FastAPI app

@pytest.fixture
def load_router_and_app():
    """Load router + FastAPI app against your local models_test.yaml."""
    router, app = _reload_with_local_models()
    yield router, app
