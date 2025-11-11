from __future__ import annotations

import os
from typing import Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

APP_NAME = os.getenv("APP_NAME", "demo-be")
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
ALLOW_ORIGINS = os.getenv("ALLOW_ORIGINS", "*").split(",")

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

# CORS (aperto di default; metti origini esplicite in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _on_startup() -> None:
    # Log minimale su boot
    print(f"[{APP_NAME}] starting… version={APP_VERSION}")


@app.get("/api/hello")
def hello() -> Dict[str, str]:
    return {"msg": "hello from demo-be"}


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/version")
def version() -> Dict[str, str]:
    return {"name": APP_NAME, "version": APP_VERSION}


# Avvio locale: uvicorn main:app --reload
# (non parte in ambienti serverizzati che importano app)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
