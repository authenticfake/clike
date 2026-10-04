import logging
import os
import time
import uuid
from fastapi import FastAPI, Request
from starlette.responses import JSONResponse

from routes.chat import router as chat_router
from routes.embeddings import router as embed_router
from routes.health import router as health_router
from routes.models import router as models_router
from routes.harper import router as harper_router
from routes.telemetry_api import router as telemetry_api_router
from routes.telemetry_ui import router as telemetry_ui_router

from middleware_security import SecureHeaders
from utils.service_auth import ServiceAuthMiddleware

from pathlib import Path
from fastapi.staticfiles import StaticFiles
from utils.model_catalog_validator import validate_catalog
from config import load_models_cfg

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("gateway")
STRICT_MODEL_CATALOG = os.getenv("STRICT_MODEL_CATALOG", "0").strip() == "1"

def _validate_catalog_on_startup() -> None:
    try:
        cfg_path = os.getenv("MODELS_CONFIG", "/workspace/configs/models.yaml")
        data, models = load_models_cfg(cfg_path)
        validation = validate_catalog(data, models)

        if validation.get("ok"):
            logger.info("model catalog validation OK: %s", validation.get("summary"))
            return

        logger.warning("model catalog validation FAILED: %s", validation)

        if STRICT_MODEL_CATALOG:
            raise RuntimeError(f"invalid model catalog: {validation.get('errors')}")
    except Exception as e:
        logger.exception("model catalog startup validation error: %s", e)
        if STRICT_MODEL_CATALOG:
            raise

        
_validate_catalog_on_startup()
app = FastAPI(title="Clike Gateway (AI Pipilines for enabling Vibe Code for StartUp & Entprise Solutions)", version="1.0.0")

app.add_middleware(SecureHeaders)
# Mount /static  (put the logo in gateway/static/clike_64x64.png)
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

class RequestLogMiddleware:
    """Logs method, path, status and latency. Never reads or logs request bodies."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = time.perf_counter()
        status = {"code": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            logger.info(
                "[HTTP] %s %s -> %s (%.0f ms)",
                scope.get("method"),
                scope.get("path"),
                status["code"],
                (time.perf_counter() - started) * 1000,
            )


# Starlette: the last middleware added is the outermost. No CORS: the APIs are
# called by the extension host and the orchestrator; the only browser page is
# the same-origin telemetry UI, which authenticates with a SameSite=Strict cookie.
app.add_middleware(
    ServiceAuthMiddleware,
    open_paths=("/health", "/v1/metrics/harper/ui", "/v1/metrics/login", "/v1/metrics/logout"),
    open_prefixes=("/static/",),
    cookie_prefixes=("/v1/metrics/",),
)
app.add_middleware(RequestLogMiddleware)


@app.exception_handler(Exception)
async def unhandled_ex_handler(request: Request, exc: Exception):
    correlation_id = uuid.uuid4().hex[:12]
    logger.exception("unhandled error correlation_id=%s", correlation_id)
    return JSONResponse(
        status_code=500,
        content={"code": "internal_error", "detail": "Internal server error", "correlation_id": correlation_id},
    )

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(embed_router)
app.include_router(models_router)
app.include_router(harper_router)
app.include_router(telemetry_api_router)
app.include_router(telemetry_ui_router)
