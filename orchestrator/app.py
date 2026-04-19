from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

import os, logging
from routes.agent import router as agent_router
from routes.git import router as git_router
from routes.health import router as health_router
from starlette.middleware.base import BaseHTTPMiddleware
from routes.v1 import router as v1_router
from config import settings
from routes.harper import router as harper_router
from routes import router as router_router
from routes import rag as rag_routes
from routes import routes_eval as eval_router
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
    if clike_mcp is not None:
        async with clike_mcp.session_manager.run():
            yield
    else:
        yield
        

app = FastAPI(title="Clike Orchestrator (AI Pipilines for enabling Vibe Code for StartUp & Entprise Solutions)",     lifespan=lifespan,
    debug=True,version="1.0.0")
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
os.makedirs(getattr(settings, "RUNS_DIR", "./runs"), exist_ok=True)
logging.getLogger("orchestrator").info("* RUNS_DIR=%s", getattr(settings, "RUNS_DIR", "./runs"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LogRequestsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Never inspect or consume MCP transport requests.
        # Mounted MCP apps may use streaming/session semantics that should stay untouched.
        if request.url.path.startswith("/mcp"):
            response = await call_next(request)
            logging.info(f"[RES] {request.method} {request.url} -> {response.status_code}")
            return response

        try:
            raw = await request.body()
            logging.info(
                f"[REQ] {request.method} {request.url} "
                f"headers={{'content-type': '{request.headers.get('content-type')}'}} "
                f"body={raw[:1000]!r}"
            )
        except Exception as e:
            logging.exception(f"Failed to read request body: {e}")

        response = await call_next(request)
        logging.info(f"[RES] {request.method} {request.url} -> {response.status_code}")
        return response
    
app.add_middleware(LogRequestsMiddleware)

# include routers
app.include_router(health_router)
app.include_router(agent_router)
app.include_router(rag_routes.router)
app.include_router(git_router)
app.include_router(v1_router)
app.include_router(harper_router)
app.include_router(router_router.router)
app.include_router(eval_router.router)



