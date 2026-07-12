import asyncio
import gc
import time

import pytest

import saffier
from saffier.core.utils.sync import force_current_loop_for_sqlalchemy, weak_subloop_map
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        name = "registry_run_sync_users"


def test_run_sync_lifecyle():
    with models.with_async_env():
        saffier.run_sync(models.create_all())
        try:
            user = saffier.run_sync(User(name="saffier").save())
            assert user
            assert saffier.run_sync(User.query.get()) == user
        finally:
            saffier.run_sync(models.drop_all())


def test_run_sync_lifecyle_sub():
    with models.with_async_env(), models.with_async_env():
        saffier.run_sync(models.create_all())
        try:
            user = saffier.run_sync(User(name="saffier").save())
            assert user
            assert saffier.run_sync(User.query.get()) == user
        finally:
            saffier.run_sync(models.drop_all())


def test_run_sync_lifecyle_with_idle_loop():
    with pytest.raises(RuntimeError):
        asyncio.get_running_loop()
    loop = asyncio.new_event_loop()
    try:
        with models.with_async_env(loop=loop):
            saffier.run_sync(models.create_all())
            try:
                user = saffier.run_sync(User(name="saffier").save())
                assert user
                assert saffier.run_sync(User.query.get()) == user
            finally:
                saffier.run_sync(models.drop_all())
    finally:
        if not loop.is_closed():
            loop.close()
    with pytest.raises(RuntimeError):
        asyncio.get_running_loop()


async def check_is_value(value):
    assert len(weak_subloop_map) == value


async def check_is_value_sub(value):
    saffier.run_sync(check_is_value(value + 1))


def test_stack():
    gc.collect()
    time.sleep(1)

    initial = len(weak_subloop_map)
    loop = asyncio.new_event_loop()
    with models.with_async_env(loop):
        assert initial == len(weak_subloop_map)
        saffier.run_sync(check_is_value(initial))
        saffier.run_sync(check_is_value_sub(initial))
    loop.close()
    del loop
    gc.collect()
    time.sleep(1)
    assert len(weak_subloop_map) <= initial


@pytest.mark.anyio
async def test_run_sync_reentry_restores_asyncio_loop_state():
    """Ensure loop re-entry does not poison later asyncio callbacks.

    Python 3.14 requires ``asyncio.timeout()`` to run while
    ``asyncio.current_task()`` is visible. The SQLAlchemy-bound sync bridge
    temporarily re-enters the running loop for deferred ORM loads. Python 3.10
    does not expose ``asyncio.timeout()``, so the fallback path still proves the
    loop class is restored after re-entry while newer runtimes also exercise the
    stricter timeout/current-task invariant.
    """

    async def use_timeout() -> str:
        """Exercise the best timeout primitive available on this Python.

        Python 3.11 and newer use ``asyncio.timeout()``, which is the code path
        asyncpg reaches on Python 3.14 and the source of the reported failure.
        Python 3.10 falls back to ``asyncio.wait_for()`` so the same test keeps
        validating that Saffier removes the temporary nested-loop patch before
        regular async execution resumes.
        """

        timeout_context = getattr(asyncio, "timeout", None)
        if timeout_context is None:
            await asyncio.wait_for(asyncio.sleep(0), timeout=1)
        else:
            async with timeout_context(1):
                await asyncio.sleep(0)
        return "ready"

    loop = asyncio.get_running_loop()

    with force_current_loop_for_sqlalchemy():
        assert saffier.run_sync(use_timeout()) == "ready"

    assert not hasattr(loop.__class__, "_nest_patched")
    assert await use_timeout() == "ready"
