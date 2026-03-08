from __future__ import annotations

import functools

import pytest

from saffier.core.events import (
    AyncLifespanContextManager,
    handle_lifespan_events,
    is_async_callable,
)


def test_is_async_callable_variants():
    async def async_fn():
        return None

    def sync_fn():
        return None

    class AsyncCallable:
        async def __call__(self):
            return None

    assert is_async_callable(async_fn) is True
    assert is_async_callable(functools.partial(async_fn)) is True
    assert is_async_callable(sync_fn) is False
    assert is_async_callable(AsyncCallable()) is True


@pytest.mark.anyio
async def test_lifespan_context_manager_runs_startup_and_shutdown():
    calls: list[str] = []

    def startup_sync():
        calls.append("startup_sync")

    async def startup_async():
        calls.append("startup_async")

    def shutdown_sync():
        calls.append("shutdown_sync")

    async def shutdown_async():
        calls.append("shutdown_async")

    manager = AyncLifespanContextManager(
        on_startup=[startup_sync, startup_async],
        on_shutdown=[shutdown_sync, shutdown_async],
    )

    async with manager(object()):
        calls.append("inside")

    assert calls == [
        "startup_sync",
        "startup_async",
        "inside",
        "shutdown_sync",
        "shutdown_async",
    ]


def test_handle_lifespan_events_paths():
    assert handle_lifespan_events(None, None, None) is None

    custom = object()
    assert handle_lifespan_events(None, None, custom) is custom

    manager = handle_lifespan_events([lambda: None], [lambda: None], None)
    assert isinstance(manager, AyncLifespanContextManager)
