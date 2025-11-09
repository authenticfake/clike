import logging
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from routes.chat import router as chat_router
from routes.embeddings import router as embed_router
from routes.health import router as health_router
from routes.models import router as models_router
from routes.harper import router as harper_router
from routes.telemetry_api import router as telemetry_api_router
from routes.telemetry_ui import router as telemetry_ui_router

from middleware_security import SecureHeaders

from pathlib import Path
from fastapi.staticfiles import StaticFiles


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("gateway")

app = FastAPI(title="Clike Gateway (AI Pipilines for enabling Vibe Code for StartUp & Entprise Solutions)", version="1.0.0")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
# Strict CORS (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "vscode-web://*"],
    allow_credentials=True,
    allow_methods=["GET","POST","OPTIONS"],
    allow_headers=["authorization","content-type","x-request-id"],
)
app.add_middleware(SecureHeaders)
# Mount /static  (metti il logo in gateway/static/clike_64x64.png)
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

class LogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            body = await request.body()
            logger.info(f"[REQ] {request.method} {request.url} ct={request.headers.get('content-type')} len={len(body)}")
        except Exception:
            logger.warning("[REQ] failed to read body for logging")
        resp = await call_next(request)
        logger.info(f"[RES] {request.method} {request.url} -> {resp.status_code}")
        return resp

app.add_middleware(LogMiddleware)

@app.exception_handler(Exception)
async def unhandled_ex_handler(request: Request, exc: Exception):
    logger.exception(f"UNHANDLED: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "code": "internal_error",
            "error": "Internal Server Error",
            "details": str(exc)[:500],
        },
    )

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(embed_router)
app.include_router(models_router)
app.include_router(harper_router)
app.include_router(telemetry_api_router)
app.include_router(telemetry_ui_router)
