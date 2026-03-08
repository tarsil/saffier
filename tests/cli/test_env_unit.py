from __future__ import annotations

import os
from pathlib import Path
from textwrap import dedent

import pytest

import saffier
from saffier.cli.constants import SAFFIER_DB, SAFFIER_EXTRA
from saffier.cli.env import MigrationEnv, Scaffold
from saffier.exceptions import CommandEnvironmentError


def _write_module(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content))


def test_import_app_from_string_requires_value():
    env = MigrationEnv()
    with pytest.raises(CommandEnvironmentError):
        env.import_app_from_string(None)


def test_import_app_from_string_loads_callable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    _write_module(
        tmp_path / "myapp.py",
        """
        class App:
            pass
        app = App()
        app._saffier_db = {"migrate": object()}
        """,
    )
    scaffold = MigrationEnv().import_app_from_string("myapp:app")
    assert isinstance(scaffold, Scaffold)
    assert scaffold.path == "myapp:app"


def test_find_app_auto_discovers_current_and_nested_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    _write_module(
        tmp_path / "app.py",
        f"""
        def app():
            return object()
        app.{SAFFIER_DB} = {{"migrate": object()}}
        """,
    )

    env = MigrationEnv()
    scaffold = env.find_app(path=None, cwd=tmp_path)
    assert scaffold.path == "app:app"

    os.remove(tmp_path / "app.py")
    _write_module(
        tmp_path / "nested" / "main.py",
        f"""
        class App:
            pass
        def get_application():
            app = App()
            app.{SAFFIER_EXTRA} = {{"extra": object()}}
            return app
        """,
    )

    scaffold_nested = env.find_app(path=None, cwd=tmp_path)
    assert scaffold_nested.path == "nested.main:get_application"


def test_find_app_raises_when_missing(tmp_path: Path):
    env = MigrationEnv()
    with pytest.raises(CommandEnvironmentError):
        env.find_app(path=None, cwd=tmp_path)


def test_load_from_env_uses_explicit_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    _write_module(
        tmp_path / "explicit.py",
        f"""
        class App:
            pass
        app = App()
        app.{SAFFIER_DB} = {{"migrate": object()}}
        """,
    )

    env = MigrationEnv()
    loaded = env.load_from_env(path="explicit:app")
    assert loaded.path == "explicit:app"


def test_import_app_from_module_path_uses_active_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.syspath_prepend(str(tmp_path))
    _write_module(
        tmp_path / "instance_module.py",
        """
        import saffier

        class App:
            pass

        app = App()
        saffier.monkay.set_instance(saffier.Instance(registry=object(), app=app, path="instance_module"))
        """,
    )

    scaffold = MigrationEnv().import_app_from_string("instance_module")

    assert isinstance(scaffold, Scaffold)
    assert scaffold.path == "instance_module"
    assert scaffold.app is not None
    saffier.monkay.set_instance(None)
