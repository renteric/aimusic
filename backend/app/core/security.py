"""
security.py - HTTP security headers middleware for AI-Music.

Registers a Starlette BaseHTTPMiddleware that adds security headers to every
response. In production a strict CSP is applied; debug mode relaxes it for
Vite HMR.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import AppConfig


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach security-related HTTP headers to every outgoing response.

    Applied as ASGI middleware so headers are present on all routes including
    FastAPI's automatic /docs and /openapi.json endpoints.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process the request and attach security headers to the response.

        Args:
            request: Incoming ASGI request.
            call_next: Next middleware / route handler in the stack.

        Returns:
            Response with security headers attached.
        """
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        if not AppConfig.DEBUG:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self' data:; "
                "connect-src 'self'; "
                "media-src 'self'; "
                "font-src 'self' data:; "
                "frame-ancestors 'none';"
            )
        return response
