import logging
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from routes.chat import router as chat_router
from routes.embeddings import router as embed_router
from routes.health import router as health_router

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("gateway")

app = FastAPI(title="Clike Gateway an AI layer for Vibe Code", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
