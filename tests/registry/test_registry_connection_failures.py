from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import saffier

pytestmark = pytest.mark.anyio


class FakeDatabase(saffier.Database):
    def __init__(self, url: str) -> None:
        super().__init__(url)
        self.is_connected = False

    async def connect(self) -> None:
        self.is_connected = True

    async def disconnect(self) -> None:
        self.is_connected = False


async def test_registry_enter_raises_and_disconnects_successful_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = saffier.Registry(
        FakeDatabase("sqlite+aiosqlite:///primary.db"),
        extra={"analytics": FakeDatabase("sqlite+aiosqlite:///analytics.db")},
    )
    disconnected: list[str] = []

    async def disconnect_primary() -> None:
        disconnected.append("primary")
        registry.database.is_connected = False

    async def connect_analytics() -> None:
        raise RuntimeError("connect-failed")

    monkeypatch.setattr(registry.database, "disconnect", disconnect_primary)
    monkeypatch.setattr(registry.extra["analytics"], "connect", connect_analytics)
    monkeypatch.setattr(registry, "reflect_pattern_models", AsyncMock())
    registry._is_automigrated = True

    with pytest.raises(RuntimeError, match="connect-failed"):
        await registry.__aenter__()

    assert disconnected == ["primary"]


async def test_registry_enter_prefers_original_connect_error_over_disconnect_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = saffier.Registry(
        FakeDatabase("sqlite+aiosqlite:///primary.db"),
        extra={"analytics": FakeDatabase("sqlite+aiosqlite:///analytics.db")},
    )

    async def disconnect_primary() -> None:
        raise RuntimeError("disconnect-failed")

    async def connect_analytics() -> None:
        raise RuntimeError("connect-failed")

    monkeypatch.setattr(registry.database, "disconnect", disconnect_primary)
    monkeypatch.setattr(registry.extra["analytics"], "connect", connect_analytics)
    monkeypatch.setattr(registry, "reflect_pattern_models", AsyncMock())
    registry._is_automigrated = True

    with pytest.raises(RuntimeError, match="connect-failed"):
        await registry.__aenter__()
