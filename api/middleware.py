"""API 中间件 -- ErrorHandlerMiddleware 空桩。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class ErrorHandlerMiddleware(BaseHTTPMiddleware):  # type: ignore[misc]
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        return await call_next(request)
