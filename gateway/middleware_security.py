# gateway/app/middleware_security.py
from starlette.middleware.base import BaseHTTPMiddleware

class SecureHeaders(BaseHTTPMiddleware):
    """Add a minimal set of HTTP security headers."""
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        return resp
