from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from starlette.responses import JSONResponse

import os, logging, time, uuid
from routes.agent import router as agent_router
from routes.health import router as health_router
from routes.v1 import router as v1_router
from config import runs_dir, settings
from routes.harper import router as harper_router
from routes import router as router_router
from routes import rag as rag_routes
from routes import routes_eval as eval_router
from services.methodologies.errors import MethodologyError
from services import gateway_http
from utils.service_auth import ServiceAuthMiddleware
try:
    from mcp_server import mcp as clike_mcp
except Exception:
    clike_mcp = None

logging.basicConfig(
    level=logging.INFO,
    format='[orchestrator] | %(levelname)-8s %(message)s',
    force=True,
)

for noisy_logger in (
    "mcp.server.streamable_http_manager",
    "mcp.server.streamable_http",
    "mcp.server.lowlevel.server",
):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

for uvicorn_logger in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logger = logging.getLogger(uvicorn_logger)
    for handler in logger.handlers:
        handler.setFormatter(logging.Formatter('[orchestrator] | %(levelname)-8s %(message)s'))
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        if clike_mcp is not None:
            async with clike_mcp.session_manager.run():
                yield
        else:
            yield
    finally:
        await gateway_http.aclose()
        

app = FastAPI(title="Clike Orchestrator (AI Pipilines for enabling Vibe Code for StartUp & Entprise Solutions)",     lifespan=lifespan,
    debug=False,version="1.0.0")
_mcp_enabled = os.getenv("CLIKE_MCP_SERVER_ENABLED", "true").lower() in {"1", "true", "yes", "on"}



if _mcp_enabled and clike_mcp is not None:
    app.mount("/mcp", clike_mcp.streamable_http_app())
    logging.getLogger("orchestrator").info("CLike * MCP mounted at /mcp/")
else:
    logging.getLogger("orchestrator").warning(
        "CLike MCP not mounted (enabled=%s available=%s)",
        _mcp_enabled,
        clike_mcp is not None,
    )
os.makedirs(runs_dir(), exist_ok=True)
logging.getLogger("orchestrator").info("* RUNS_DIR=%s", runs_dir())
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
            logging.info(
                "[HTTP] %s %s -> %s (%.0f ms)",
                scope.get("method"),
                scope.get("path"),
                status["code"],
                (time.perf_counter() - started) * 1000,
            )


# Starlette: the last middleware added is the outermost. Logging wraps auth so
# rejected requests are logged too. No CORS: only the extension host and the
# CLike services call these APIs (never a browser page).
app.add_middleware(ServiceAuthMiddleware, open_paths=("/health",))
app.add_middleware(RequestLogMiddleware)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    correlation_id = uuid.uuid4().hex[:12]
    logging.getLogger("orchestrator").exception("unhandled error correlation_id=%s", correlation_id)
    return JSONResponse(
        status_code=500,
        content={"code": "internal_error", "detail": "Internal server error", "correlation_id": correlation_id},
    )


@app.exception_handler(MethodologyError)
async def methodology_error_handler(request: Request, exc: MethodologyError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})

# include routers
app.include_router(health_router)
app.include_router(agent_router)
app.include_router(rag_routes.router)
app.include_router(v1_router)
app.include_router(harper_router)
app.include_router(router_router.router)
app.include_router(eval_router.router)


