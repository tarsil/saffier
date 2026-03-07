from __future__ import annotations

import types
from pathlib import Path
from textwrap import dedent

import pytest

from saffier.cli import cli as saffier_cli_mod
from saffier.conf import reload_settings
from saffier.exceptions import CommandEnvironmentError


def _write_module(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content))


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SAFFIER_SETTINGS_MODULE", "tests.settings.TestSettings")
    reload_settings()
    yield
    monkeypatch.setenv("SAFFIER_SETTINGS_MODULE", "tests.settings.TestSettings")
    reload_settings()


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
    monkeypatch.setattr(saffier_cli_mod, "evaluate_settings_once_ready", lambda: None)
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
    monkeypatch.setattr(saffier_cli_mod, "evaluate_settings_once_ready", lambda: None)
    monkeypatch.setattr(saffier_cli_mod.MigrationEnv, "load_from_env", lambda self, path=None: env)
    called = {"set": None}
    monkeypatch.setattr(
        saffier_cli_mod, "set_migration_env", lambda value: called.update({"set": value})
    )

    saffier_cli_mod.saffier_callback(ctx, app="app:main")
    assert ctx.obj is env
    assert called["set"] is env


def test_cli_callback_skips_app_loading_for_init(monkeypatch: pytest.MonkeyPatch):
    ctx = types.SimpleNamespace(obj=None)
    monkeypatch.setattr(
        saffier_cli_mod,
        "sys",
        types.SimpleNamespace(argv=["saffier", "init"], exit=lambda code: None),
    )
    called = {"clear": False, "evaluate": False}
    monkeypatch.setattr(
        saffier_cli_mod, "clear_migration_env", lambda: called.update({"clear": True})
    )
    monkeypatch.setattr(
        saffier_cli_mod, "evaluate_settings_once_ready", lambda: called.update({"evaluate": True})
    )

    saffier_cli_mod.saffier_callback(ctx, app=None)

    assert called == {"clear": True, "evaluate": False}
    assert ctx.obj is None


def test_cli_callback_uses_preloaded_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    _write_module(
        tmp_path / "preloaded_cli_app.py",
        """
        from types import SimpleNamespace

        from saffier.conf import _monkay

        class App:
            pass

        app = App()
        app._saffier_db = {"migrate": object()}
        _monkay.set_instance(SimpleNamespace(app=app, path="preloaded_cli_app:app"), apply_extensions=False)
        """,
    )
    _write_module(
        tmp_path / "preloaded_cli_settings.py",
        """
        from saffier.conf.global_settings import SaffierSettings

        class Settings(SaffierSettings):
            preloads = ("preloaded_cli_app",)
        """,
    )

    monkeypatch.setenv("SAFFIER_SETTINGS_MODULE", "preloaded_cli_settings.Settings")
    ctx = types.SimpleNamespace(obj=None)
    monkeypatch.setattr(
        saffier_cli_mod,
        "sys",
        types.SimpleNamespace(argv=["saffier", "migrate"], exit=lambda code: None),
    )
    called = {"set": None}
    monkeypatch.setattr(
        saffier_cli_mod, "set_migration_env", lambda value: called.update({"set": value})
    )

    saffier_cli_mod.saffier_callback(ctx, app=None)

    assert ctx.obj.path == "preloaded_cli_app:app"
    assert called["set"].path == "preloaded_cli_app:app"
