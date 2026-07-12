"""Synchronous bridge helpers for Saffier's async SQLAlchemy runtime.

Saffier exposes ``run_sync`` for applications and tests that need to call async
ORM APIs from synchronous code. The bridge normally moves work to a helper event
loop, but SQLAlchemy async connections are loop-bound, so active transaction
contexts must be re-entered on their owning loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import weakref
from collections.abc import Awaitable, Iterable, Iterator
from contextvars import ContextVar, Token, copy_context
from threading import Event, Thread
from typing import Any

_MISSING: Any = object()
_LOOP_REENTRY_ATTRS = (
    "run_forever",
    "run_until_complete",
    "_run_once",
    "_check_running",
    "_check_runnung",
    "_num_runs_pending",
    "_is_proactorloop",
    "_nest_patched",
)
_ASYNCIO_REENTRY_ATTRS = (
    (asyncio, ("Task", "Future", "run", "get_event_loop", "_nest_patched")),
    (asyncio.tasks, ("Task", "_CTask", "_current_tasks")),
    (asyncio.futures, ("Future", "_CFuture")),
    (asyncio.events, ("get_event_loop", "_get_event_loop")),
)

current_eventloop: ContextVar[asyncio.AbstractEventLoop | None] = ContextVar(
    "current_eventloop", default=None
)
_SQLALCHEMY_SYNC_BRIDGE_DEPTH: ContextVar[int] = ContextVar(
    "_SQLALCHEMY_SYNC_BRIDGE_DEPTH", default=0
)


@contextlib.contextmanager
def force_current_loop_for_sqlalchemy() -> Iterator[None]:
    """Force ``run_sync`` to execute the awaitable on the current loop.

    SQLAlchemy async engines and driver connections are bound to the event loop
    that created or checked them out. ORM lazy-loading paths use this context
    when synchronous attribute access has to await database work from inside an
    already-running loop.
    """
    token: Token[int] = _SQLALCHEMY_SYNC_BRIDGE_DEPTH.set(_SQLALCHEMY_SYNC_BRIDGE_DEPTH.get() + 1)
    try:
        yield
    finally:
        _SQLALCHEMY_SYNC_BRIDGE_DEPTH.reset(token)


def should_force_current_loop_for_sqlalchemy() -> bool:
    """Return whether the current ``run_sync`` call is SQLAlchemy-bound.

    The flag is deliberately explicit instead of applying to every nested
    ``run_sync`` call. Generic synchronous bridge calls still use the helper
    loop, while ORM database lazy loads stay on the loop that owns SQLAlchemy's
    async resources.
    """
    return _SQLALCHEMY_SYNC_BRIDGE_DEPTH.get() > 0


def _snapshot_attrs(target: Any, names: Iterable[str]) -> tuple[tuple[Any, str, Any], ...]:
    """Capture object attributes before a temporary asyncio re-entry patch.

    ``nest_asyncio`` makes both module-level and event-loop-class changes. The
    sync bridge only needs those changes while one SQLAlchemy-bound coroutine is
    being driven to completion, so Saffier records every attribute that may be
    touched before applying the patch.

    Args:
        target: Module, class, or object whose attributes should be captured.
        names: Attribute names that may be replaced or created by the patch.

    Returns:
        tuple[tuple[Any, str, Any], ...]: Snapshot entries containing the target,
        attribute name, and previous value. A private sentinel is stored when
        the attribute did not exist so restoration can delete patch-created
        attributes instead of leaving false state behind.
    """
    return tuple((target, name, getattr(target, name, _MISSING)) for name in names)


def _restore_attrs(snapshot: Iterable[tuple[Any, str, Any]]) -> None:
    """Restore attributes captured by ``_snapshot_attrs()``.

    Restoration is deliberately value-based instead of assuming the unpatched
    stdlib shape. That matters in embedded environments, test harnesses, and
    interactive shells where another tool may already have installed a custom
    event-loop policy or task implementation before Saffier enters the bridge.

    Args:
        snapshot: Entries returned by ``_snapshot_attrs()``.
    """
    for target, name, value in snapshot:
        if value is _MISSING:
            with contextlib.suppress(AttributeError):
                delattr(target, name)
        else:
            setattr(target, name, value)


@contextlib.contextmanager
def _temporary_loop_reentry(loop: asyncio.AbstractEventLoop) -> Iterator[None]:
    """Temporarily allow one running event loop to be re-entered.

    SQLAlchemy async connections and asyncpg driver objects are tied to the
    event loop that owns them. When synchronous ORM surfaces such as deferred
    attribute access need to await work while a transaction-bound connection is
    active, moving the coroutine to Saffier's helper loop would cross event-loop
    ownership and fail.

    ``nest_asyncio`` provides the required re-entry mechanics, but its public
    ``apply()`` function also changes the event-loop policy and leaves all
    mutations in place. Python 3.14 exposes that as a hard failure because
    asyncpg uses ``asyncio.timeout()``, which now requires
    ``asyncio.current_task()`` to remain visible while callbacks run. This
    context manager uses only the patch pieces needed for one nested
    ``run_until_complete()`` call and restores the previous loop, task, future,
    and ``asyncio.run()`` state before normal async execution resumes.

    Args:
        loop: Running event loop that owns the SQLAlchemy resources being used
            by the synchronous bridge.
    """
    import nest_asyncio

    loop_snapshot = _snapshot_attrs(loop.__class__, _LOOP_REENTRY_ATTRS)
    asyncio_snapshot: list[tuple[Any, str, Any]] = []
    for target, names in _ASYNCIO_REENTRY_ATTRS:
        asyncio_snapshot.extend(_snapshot_attrs(target, names))

    try:
        nest_asyncio._patch_asyncio()
        nest_asyncio._patch_loop(loop)
        yield
    finally:
        _restore_attrs(asyncio_snapshot)
        _restore_attrs(loop_snapshot)


async def _coro_helper(awaitable: Awaitable, timeout: float | None) -> Any:
    """Await one object while applying Saffier's optional timeout behavior.

    The helper keeps timeout handling identical across direct ``asyncio.run``,
    inactive-loop ``run_until_complete``, helper-loop execution, and re-entered
    SQLAlchemy transaction loops.
    """
    if timeout is not None and timeout > 0:
        return await asyncio.wait_for(awaitable, timeout)
    return await awaitable


weak_subloop_map: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, asyncio.AbstractEventLoop
] = weakref.WeakKeyDictionary()


async def _startup(old_loop: asyncio.AbstractEventLoop, is_initialized: Event) -> None:
    """Register a helper loop that lives as long as its parent loop.

    Saffier's traditional sync bridge uses a background event loop per active
    parent loop. The helper is recorded in ``weak_subloop_map`` and stops itself
    once the parent loop closes.
    """
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
    """Create and run the background helper loop for a parent event loop.

    This function is the target for a daemon thread. It publishes the helper
    loop through ``_startup()``, runs it until shutdown, then closes async
    generators and removes the weak-map entry during cleanup.
    """
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
    """Return the helper event loop paired with a parent loop.

    A helper loop is created lazily on first use and then reused for later sync
    bridge calls. Reuse avoids repeatedly starting threads while preserving the
    old context-copying behavior for non-SQLAlchemy-bound calls.
    """
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

    When SQLAlchemy async connections are bound to the current context, Saffier
    re-enters the running loop instead of copying context into a helper loop.
    This keeps loop-bound SQLAlchemy transactions and asyncpg futures on the
    loop that owns them while preserving the helper-loop behavior for unrelated
    synchronous bridge calls.
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
    if not loop.is_closed():
        try:
            from saffier.core.connection.database import should_reenter_sync_bridge
        except Exception:
            should_reenter = False
        else:
            should_reenter = (
                should_force_current_loop_for_sqlalchemy() or should_reenter_sync_bridge()
            )
        if not should_reenter:
            ctx = copy_context()
            return asyncio.run_coroutine_threadsafe(
                ctx.run(_coro_helper, awaitable, timeout), get_subloop(loop)
            ).result()

        with _temporary_loop_reentry(loop):
            return loop.run_until_complete(_coro_helper(awaitable, timeout))

    ctx = copy_context()
    return asyncio.run_coroutine_threadsafe(
        ctx.run(_coro_helper, awaitable, timeout), get_subloop(loop)
    ).result()
