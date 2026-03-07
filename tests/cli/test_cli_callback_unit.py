from __future__ import annotations

import types

import pytest

from saffier.cli import cli as saffier_cli_mod
from saffier.exceptions import CommandEnvironmentError


def test_cli_callback_skips_when_help(monkeypatch: pytest.MonkeyPatch):
    ctx = types.SimpleNamespace(obj=None)
    monkeypatch.setattr(
        saffier_cli_mod,
        "sys",
        types.SimpleNamespace(argv=["saffier", "--help"], exit=lambda code: None),
    )
    saffier_cli_mod.saffier_callback(ctx, app=None)
    assert ctx.obj is None


def test_cli_callback_handles_environment_error(monkeypatch: pytest.MonkeyPatch):
    ctx = types.SimpleNamespace(obj=None)
    monkeypatch.setattr(
        saffier_cli_mod,
        "sys",
        types.SimpleNamespace(
            argv=["saffier", "upgrade"], exit=lambda code: (_ for _ in ()).throw(SystemExit(code))
        ),
    )
    monkeypatch.setattr(
        saffier_cli_mod.MigrationEnv,
        "load_from_env",
        lambda self, path=None: (_ for _ in ()).throw(CommandEnvironmentError("bad env")),
    )
    monkeypatch.setattr(saffier_cli_mod, "error", lambda message: None)

    with pytest.raises(SystemExit):
        saffier_cli_mod.saffier_callback(ctx, app=None)


def test_cli_callback_sets_context(monkeypatch: pytest.MonkeyPatch):
    ctx = types.SimpleNamespace(obj=None)
    env = object()
    monkeypatch.setattr(
        saffier_cli_mod,
        "sys",
        types.SimpleNamespace(argv=["saffier", "upgrade"], exit=lambda code: None),
    )
    monkeypatch.setattr(saffier_cli_mod.MigrationEnv, "load_from_env", lambda self, path=None: env)
    called = {"set": None}
    monkeypatch.setattr(
        saffier_cli_mod, "set_migration_env", lambda value: called.update({"set": value})
    )

    saffier_cli_mod.saffier_callback(ctx, app="app:main")
    assert ctx.obj is env
    assert called["set"] is env
