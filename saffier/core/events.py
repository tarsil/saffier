import functools
import inspect
import typing
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

Scope = typing.MutableMapping[str, typing.Any]
Message = typing.MutableMapping[str, typing.Any]

Receive = typing.Callable[[], typing.Awaitable[Message]]
Send = typing.Callable[[Message], typing.Awaitable[None]]

_T = TypeVar("_T")


def is_async_callable(obj: typing.Any) -> bool:
    while isinstance(obj, functools.partial):
        obj = obj.func

    return inspect.iscoroutinefunction(obj) or (
        callable(obj) and inspect.iscoroutinefunction(obj.__call__)
    )


class AyncLifespanContextManager:
    """Compatibility lifespan context manager for startup and shutdown hooks.

    Older Saffier integrations often still expose Starlette-style `on_startup`
    and `on_shutdown` lists. This wrapper adapts those handlers into the newer
    lifespan protocol without forcing applications to rewrite their bootstrap
    code immediately.
    """

    def __init__(
        self,
        on_shutdown: Sequence[Callable[..., Any]] | None = None,
        on_startup: Sequence[Callable[..., Any]] | None = None,
    ) -> None:
        self.on_startup = [] if on_startup is None else list(on_startup)
        self.on_shutdown = [] if on_shutdown is None else list(on_shutdown)

    def __call__(self: _T, app: object) -> _T:
        return self

    async def __aenter__(self) -> None:
        """Run all configured startup handlers."""
        for handler in self.on_startup:
            if is_async_callable(handler):
                await handler()
            else:
                handler()

    async def __aexit__(self, scope: Scope, receive: Receive, send: Send, **kwargs: Any) -> None:
        """Run all configured shutdown handlers."""
        for handler in self.on_shutdown:
            if is_async_callable(handler):
                await handler()
            else:
                handler()


def handle_lifespan_events(
    on_startup: Sequence[Callable] | None = None,
    on_shutdown: Sequence[Callable] | None = None,
    lifespan: Any | None = None,
) -> Any:
    """Handles with the lifespan events in the new Starlette format of lifespan.
    This adds a mask that keeps the old `on_startup` and `on_shutdown` events variable
    declaration for legacy and comprehension purposes and build the async context manager
    for the lifespan.
    """
    if on_startup or on_shutdown:
        return AyncLifespanContextManager(on_startup=on_startup, on_shutdown=on_shutdown)
    elif lifespan:
        return lifespan
    return None
