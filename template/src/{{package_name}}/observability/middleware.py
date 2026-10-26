import time

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .logs import get_logger

_logger = get_logger(__name__)
_SKIP_PATHS = ("/health/",)


class RequestLoggingMiddleware:
    """One structured log line per HTTP request, inside the request's span."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get("path", "")
        if scope["type"] != "http" or path.startswith(_SKIP_PATHS):
            await self.app(scope, receive, send)
            return

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(http_method=scope["method"], http_path=path)
        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _logger.info(
                "http.request",
                http_status=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
