from __future__ import annotations

import base64
import secrets
from typing import Any


class BasicAuthMiddleware:
    """Minimal ASGI middleware implementing HTTP Basic auth for the admin app.

    The middleware protects only HTTP requests and returns a standard `401`
    challenge when credentials are missing or invalid.
    """

    def __init__(self, app: Any, *, username: str = "admin", password: str) -> None:
        """Store the downstream app and expected Basic auth credentials.

        Credentials are encoded once during middleware construction so each
        request only needs a constant-time comparison against the incoming
        header value.

        Args:
            app: Downstream ASGI application.
            username: Expected Basic auth username.
            password: Expected Basic auth password.
        """
        self.app = app
        self.basic_string = base64.b64encode(f"{username}:{password}".encode()).decode()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        """Authorize one ASGI request before dispatching downstream.

        Non-HTTP scopes are passed through unchanged. HTTP requests must provide
        a Basic authorization header whose credentials match the configured
        values, otherwise the middleware emits a challenge response.

        Args:
            scope: ASGI connection scope.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin1").lower(): value.decode("latin1")
            for key, value in scope.get("headers", [])
        }
        auth = headers.get("authorization")

        if not auth:
            await self._deny(send)
            return

        try:
            scheme, credentials = auth.split(" ", 1)
        except ValueError:
            await self._deny(send)
            return

        if scheme.lower() != "basic" or not secrets.compare_digest(credentials, self.basic_string):
            await self._deny(send)
            return

        await self.app(scope, receive, send)

    async def _deny(self, send: Any) -> None:
        """Emit the Basic auth challenge response.

        Args:
            send: ASGI send callable receiving the response start and body
                messages.
        """
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"www-authenticate", b'Basic realm="Saffier Admin", charset="UTF-8"'),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"Unauthorized"})
