from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import logging
from routes.agent import router as agent_router
from routes.rag import router as rag_router
from routes.git import router as git_router
from routes.health import router as health_router
from starlette.middleware.base import BaseHTTPMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Clike Orchestrator (AI Layer enabling Vibe Code)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
class LogRequestsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            raw = await request.body()
            logging.info(f"[REQ] {request.method} {request.url} headers={{'content-type': '{request.headers.get('content-type')}'}} body={raw[:1000]!r}")
        except Exception as e:
            logging.exception(f"Failed to read request body: {e}")
        response = await call_next(request)
        logging.info(f"[RES] {request.method} {request.url} -> {response.status_code}")
        return response

app.add_middleware(LogRequestsMiddleware)
# include routers
app.include_router(health_router)
app.include_router(agent_router)
app.include_router(rag_router)
app.include_router(git_router)
