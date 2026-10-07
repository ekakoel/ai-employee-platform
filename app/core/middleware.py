"""HTTP middleware: request ID + auth bootstrap from Bearer."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.security import decode_access_token

logger = logging.getLogger("app.access")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={"request_id": request_id},
        )
        return response


class AuthBootstrapMiddleware(BaseHTTPMiddleware):
    """
    If Authorization Bearer is present and X-User-ID is missing,
    inject X-User-ID from JWT subject so existing route handlers work.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        xuid = request.headers.get("x-user-id") or request.headers.get("X-User-ID")
        if auth and auth.lower().startswith("bearer ") and not xuid:
            token = auth.split(" ", 1)[1].strip()
            try:
                payload = decode_access_token(token)
                sub = payload.get("sub")
                if sub:
                    # MutableHeaders
                    headers = request.scope.setdefault("headers", [])
                    headers.append((b"x-user-id", str(sub).encode("latin-1")))
            except Exception:
                pass
        return await call_next(request)
