from __future__ import annotations

import asyncio
import weakref
from collections.abc import Awaitable
from contextvars import ContextVar, copy_context
from threading import Event, Thread
from typing import Any

current_eventloop: ContextVar[asyncio.AbstractEventLoop | None] = ContextVar(
    "current_eventloop", default=None
)


async def _coro_helper(awaitable: Awaitable, timeout: float | None) -> Any:
    if timeout is not None and timeout > 0:
        return await asyncio.wait_for(awaitable, timeout)
    return await awaitable


weak_subloop_map: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, asyncio.AbstractEventLoop
] = weakref.WeakKeyDictionary()


async def _startup(old_loop: asyncio.AbstractEventLoop, is_initialized: Event) -> None:
    new_loop = asyncio.get_running_loop()
    weakref.finalize(old_loop, new_loop.stop)
    weak_subloop_map[old_loop] = new_loop
    is_initialized.set()
    while True:
        if not old_loop.is_closed():
            await asyncio.sleep(0.5)
        else:
            break
    new_loop.stop()


def _init_thread(old_loop: asyncio.AbstractEventLoop, is_initialized: Event) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task = loop.create_task(_startup(old_loop, is_initialized))
    try:
        try:
            loop.run_forever()
        except RuntimeError:
            pass
        finally:
            is_initialized.clear()
            loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        weak_subloop_map.pop(loop, None)
        del task
        loop.close()
        del loop


def get_subloop(loop: asyncio.AbstractEventLoop) -> asyncio.AbstractEventLoop:
    sub_loop = weak_subloop_map.get(loop)
    if sub_loop is None:
        is_initialized = Event()
        thread = Thread(target=_init_thread, args=[loop, is_initialized], daemon=True)
        thread.start()
        is_initialized.wait()
        return weak_subloop_map[loop]
    return sub_loop


def run_sync(
    awaitable: Awaitable,
    timeout: float | None = None,
    *,
    loop: asyncio.AbstractEventLoop | None = None,
) -> Any:
    """
    Runs an awaitable from synchronous code, reusing or bridging event loops when needed.
    """
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = current_eventloop.get()

    if loop is None:
        return asyncio.run(_coro_helper(awaitable, timeout))
    if not loop.is_closed() and not loop.is_running():
        return loop.run_until_complete(_coro_helper(awaitable, timeout))

    ctx = copy_context()
    return asyncio.run_coroutine_threadsafe(
        ctx.run(_coro_helper, awaitable, timeout), get_subloop(loop)
    ).result()
