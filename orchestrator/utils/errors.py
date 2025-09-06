# -*- coding: utf-8 -*-
from fastapi import Request
from fastapi.responses import JSONResponse
import uuid
import logging

log = logging.getLogger("orchestrator")

def error_response(code: str, message: str, status: int, details: dict | None = None, retryable: bool = False):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": f"req_{uuid.uuid4().hex[:12]}",
                "retryable": retryable
            }
        },
    )

async def http_exception_handler(request: Request, exc):
    # Generic fallback
    log.exception("Unhandled error: %s", exc)
    return error_response("SERVER_ERROR", "Unexpected server error", 500)

def install_exception_handlers(app):
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(StarletteHTTPException)
    async def _starlette_handler(request: Request, exc: StarletteHTTPException):
        return error_response("HTTP_ERROR", exc.detail or "HTTP error", exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        return error_response("VALIDATION_ERROR", "Invalid request", 422, {"errors": exc.errors()})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        return await http_exception_handler(request, exc)
