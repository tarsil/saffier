from __future__ import annotations

import base64
import secrets
from typing import Any


class BasicAuthMiddleware:
    """
    Minimal ASGI middleware for HTTP Basic auth.
    """

    def __init__(self, app: Any, *, username: str = "admin", password: str) -> None:
        self.app = app
        self.basic_string = base64.b64encode(f"{username}:{password}".encode()).decode()

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
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
