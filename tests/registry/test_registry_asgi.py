from __future__ import annotations

from typing import Any

import pytest

import saffier

pytestmark = pytest.mark.anyio


class TrackingRegistry(saffier.Registry):
    """Registry subclass that records ASGI lifecycle entry and exit.

    The test exercises the public ``Registry.asgi`` wrapper without opening a
    real database connection. Overriding the async context methods keeps the
    assertion focused on the ASGI lifespan contract.
    """

    def __init__(self) -> None:
        """Initialize the registry with counters for lifecycle assertions."""
        super().__init__("sqlite+aiosqlite:///:memory:")
        self.entered = 0
        self.exited = 0

    async def __aenter__(self) -> TrackingRegistry:
        """Record that the registry lifespan has started.

        Returns:
            TrackingRegistry: Current registry instance.
        """
        self.entered += 1
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        """Record that the registry lifespan has finished.

        Args:
            *args: Exception information supplied by async context manager
                protocol.
            **kwargs: Additional context manager values.
        """
        self.exited += 1


async def test_registry_asgi_wraps_lifespan_context() -> None:
    """Verify ``Registry.asgi`` enters and exits during ASGI lifespan.

    The wrapper is driven with raw lifespan messages so the test proves the
    public ASGI callable manages registry startup and shutdown directly.
    """
    registry = TrackingRegistry()
    downstream_calls: list[str] = []

    async def app(scope, receive, send) -> None:
        """Record non-lifespan calls made to the downstream app.

        Args:
            scope: ASGI scope.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        downstream_calls.append(scope["type"])

    wrapped = registry.asgi(app, handle_lifespan=True)
    messages = iter(
        [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
    )
    sent: list[dict[str, str]] = []

    async def receive() -> dict[str, str]:
        """Return the next lifespan message for the wrapped app.

        Returns:
            dict[str, str]: ASGI lifespan message.
        """
        return next(messages)

    async def send(message: dict[str, str]) -> None:
        """Collect messages emitted by the wrapped app.

        Args:
            message: ASGI message emitted by the wrapper.
        """
        sent.append(message)

    await wrapped({"type": "lifespan"}, receive, send)

    assert registry.entered == 1
    assert registry.exited == 1
    assert downstream_calls == []
    assert sent == [
        {"type": "lifespan.startup.complete"},
        {"type": "lifespan.shutdown.complete"},
    ]


async def test_registry_asgi_can_return_decorator_factory() -> None:
    """Verify ``Registry.asgi`` supports decorator-style wrapping.

    Applications can call ``registry.asgi()`` first and apply the returned
    factory later. This mirrors Saffier's database-level ASGI integration and
    keeps app factories ergonomic.
    """
    registry = TrackingRegistry()

    async def app(scope, receive, send) -> None:
        """Minimal downstream ASGI app for decorator-style wrapping.

        Args:
            scope: ASGI scope.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    factory = registry.asgi(handle_lifespan=True)
    wrapped = factory(app)
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        """Return a single request body message.

        Returns:
            dict[str, Any]: Empty HTTP request body message.
        """
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        """Collect HTTP messages emitted by the wrapped app.

        Args:
            message: ASGI message emitted by the app.
        """
        sent.append(message)

    await wrapped({"type": "http", "method": "GET", "path": "/"}, receive, send)

    assert sent[0]["status"] == 204
