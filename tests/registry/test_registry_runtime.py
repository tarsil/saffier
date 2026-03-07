from __future__ import annotations

import asyncio
from typing import Any

import pytest

import saffier
from saffier.conf import _monkay, override_settings
from saffier.conf.global_settings import SaffierSettings


class FakeDatabase(saffier.Database):
    def __init__(self, url: str) -> None:
        super().__init__(url)
        self.is_connected = False
        self.connect_calls = 0
        self.disconnect_calls = 0

    async def connect(self) -> None:
        self.is_connected = True
        self.connect_calls += 1

    async def disconnect(self) -> None:
        self.is_connected = False
        self.disconnect_calls += 1


@pytest.fixture(autouse=True)
def clear_active_instance() -> None:
    _monkay.set_instance(None, apply_extensions=False)
    yield
    _monkay.set_instance(None, apply_extensions=False)


def test_registry_rejects_invalid_extra_names() -> None:
    with pytest.raises(AssertionError):
        saffier.Registry(
            database=FakeDatabase("sqlite+aiosqlite:///main.db"),
            extra={"": FakeDatabase("sqlite+aiosqlite:///extra.db")},
        )


def test_registry_warns_for_extra_names_with_whitespace(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING")

    registry = saffier.Registry(
        database=FakeDatabase("sqlite+aiosqlite:///main.db"),
        extra={" another ": FakeDatabase("sqlite+aiosqlite:///extra.db")},
    )

    assert str(registry.extra[" another "].url) == "sqlite+aiosqlite:///extra.db"
    assert "starts or ends with whitespace characters" in caplog.text


@pytest.mark.anyio
async def test_registry_automigrate_runs_once(monkeypatch: pytest.MonkeyPatch) -> None:
    class MigrationSettings(SaffierSettings):
        migration_directory = "auto_migrations"

    database = FakeDatabase("sqlite+aiosqlite:///main.db")
    registry = saffier.Registry(database=database, automigrate_config=MigrationSettings)

    async def fake_reflect(*args: Any, **kwargs: Any) -> None:
        del args, kwargs

    async def fake_to_thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    calls: list[tuple[bool, str]] = []

    def fake_upgrade(app: Any = None, **kwargs: Any) -> None:
        del app, kwargs
        calls.append((_monkay.instance.registry is registry, _monkay.settings.migration_directory))

    monkeypatch.setattr(registry, "reflect_pattern_models", fake_reflect)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr("saffier.cli.base.upgrade", fake_upgrade)

    with override_settings(allow_automigrations=True, migration_directory="outer_migrations"):
        async with registry:
            assert database.is_connected
        async with registry:
            pass

    assert calls == [(True, "auto_migrations")]
    assert database.connect_calls == 2
    assert database.disconnect_calls == 2


@pytest.mark.anyio
async def test_registry_automigrate_respects_runtime_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MigrationSettings(SaffierSettings):
        migration_directory = "auto_migrations"

    database = FakeDatabase("sqlite+aiosqlite:///main.db")
    registry = saffier.Registry(database=database, automigrate_config=MigrationSettings)

    async def fake_reflect(*args: Any, **kwargs: Any) -> None:
        del args, kwargs

    calls: list[str] = []

    def fake_upgrade(app: Any = None, **kwargs: Any) -> None:
        del app, kwargs
        calls.append("upgrade")

    monkeypatch.setattr(registry, "reflect_pattern_models", fake_reflect)
    monkeypatch.setattr("saffier.cli.base.upgrade", fake_upgrade)

    with override_settings(allow_automigrations=False):
        async with registry:
            assert database.is_connected

    assert calls == []
    assert registry._is_automigrated is True
