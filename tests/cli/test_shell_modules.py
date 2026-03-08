from __future__ import annotations

import types
from types import SimpleNamespace

import pytest

from saffier.cli.operations.shell.base import handle_lifespan_events, run_shell, shell
from saffier.cli.operations.shell.ipython import get_ipython, get_ipython_arguments
from saffier.cli.operations.shell.ptpython import get_ptpython, vi_mode
from saffier.cli.operations.shell.utils import import_objects
from saffier.core.events import AyncLifespanContextManager


class _DummyRegistry:
    def __init__(self) -> None:
        self.models = {}
        self.reflected = {}


def test_handle_lifespan_events_behaviour():
    custom = object()
    assert handle_lifespan_events(lifespan=custom) is custom

    manager = handle_lifespan_events(on_startup=[lambda: None], on_shutdown=[lambda: None])
    assert isinstance(manager, AyncLifespanContextManager)


def test_shell_rejects_invalid_kernel(monkeypatch: pytest.MonkeyPatch):
    from saffier.cli.operations.shell import base as shell_base

    monkeypatch.setattr(shell_base, "error", lambda message: None)
    ctx = SimpleNamespace(command=SimpleNamespace(params=[]))
    with pytest.raises(SystemExit):
        shell.callback.__wrapped__(ctx, kernel="invalid")


def test_shell_executes_stdin_in_non_interactive_mode(monkeypatch: pytest.MonkeyPatch):
    from saffier.cli.operations.shell import base as shell_base

    fake_app = SimpleNamespace(_saffier_db={"migrate": SimpleNamespace(registry="registry")})
    fake_stdin = SimpleNamespace(
        isatty=lambda: False,
        read=lambda: "_stdin_exec_marker = True",
    )

    monkeypatch.setattr(shell_base, "get_migration_app", lambda: fake_app)
    monkeypatch.setattr(shell_base, "get_migration_registry", lambda: "registry")
    monkeypatch.setattr(shell_base.sys, "platform", "linux")
    monkeypatch.setattr(shell_base.sys, "stdin", fake_stdin)
    monkeypatch.setattr(shell_base.select, "select", lambda *_: ([fake_stdin], [], []))

    ctx = SimpleNamespace(command=SimpleNamespace(params=[]))
    shell.callback.__wrapped__(ctx, kernel="ipython")
    assert shell_base.__dict__.pop("_stdin_exec_marker", False) is True


def test_shell_uses_extra_registry_and_runs_execsync(monkeypatch: pytest.MonkeyPatch):
    from saffier.cli.operations.shell import base as shell_base

    fake_app = SimpleNamespace(
        _saffier_extra={"extra": SimpleNamespace(registry="extra-registry")},
        on_startup=["startup"],
        on_shutdown=["shutdown"],
        lifespan=None,
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(shell_base, "get_migration_app", lambda: fake_app)
    monkeypatch.setattr(shell_base, "get_migration_registry", lambda: "extra-registry")
    monkeypatch.setattr(shell_base.sys, "platform", "linux")
    monkeypatch.setattr(shell_base.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(
        shell_base,
        "handle_lifespan_events",
        lambda **kwargs: captured.setdefault("lifespan_kwargs", kwargs) or "lifespan-token",
    )

    def _execsync(fn):
        assert fn is shell_base.run_shell
        return lambda app, lifespan, registry, kernel: captured.update(
            {
                "app": app,
                "lifespan": lifespan,
                "registry": registry,
                "kernel": kernel,
            }
        )

    monkeypatch.setattr(shell_base, "execsync", _execsync)

    ctx = SimpleNamespace(command=SimpleNamespace(params=[]))
    result = shell.callback.__wrapped__(ctx, kernel="ptpython")

    assert result is None
    assert captured["registry"] == "extra-registry"
    assert captured["kernel"] == "ptpython"
    assert captured["lifespan_kwargs"] == {
        "on_startup": ["startup"],
        "on_shutdown": ["shutdown"],
        "lifespan": None,
    }


def test_import_objects_includes_defaults_and_models(monkeypatch: pytest.MonkeyPatch):
    class DummyModel:
        __name__ = "DummyModel"
        __module__ = "tests.mod"

    class DummyReflected:
        __name__ = "DummyReflected"
        __module__ = "tests.mod"

    registry = _DummyRegistry()
    registry.models["DummyModel"] = DummyModel
    registry.reflected["DummyReflected"] = DummyReflected

    messages: list[str] = []
    from saffier.cli.operations.shell import utils as shell_utils

    monkeypatch.setattr(shell_utils, "welcome_message", lambda app: None)
    monkeypatch.setattr(
        shell_utils.printer, "write_success", lambda message, **kwargs: messages.append(message)
    )

    imported = import_objects(SimpleNamespace(__class__=SimpleNamespace(__name__="App")), registry)
    assert "datetime" in imported
    assert "Model" in imported
    assert "DummyModel" in imported
    assert "DummyReflected" in imported
    assert any("Models" in item for item in messages)


def test_get_ipython_arguments(monkeypatch: pytest.MonkeyPatch):
    from saffier.cli.operations.shell import ipython as ipy

    monkeypatch.setattr(ipy.settings, "ipython_args", [])
    monkeypatch.setenv("IPYTHON_ARGUMENTS", "--quiet --no-autoindent")
    assert get_ipython_arguments() == ["--quiet", "--no-autoindent"]


def test_get_ipython_runner(monkeypatch: pytest.MonkeyPatch):
    from saffier.cli.operations.shell import ipython as ipy

    calls: dict[str, object] = {}
    fake_mod = types.SimpleNamespace(
        start_ipython=lambda argv, user_ns: calls.update({"argv": argv, "ns": user_ns})
    )
    monkeypatch.setitem(__import__("sys").modules, "IPython", fake_mod)
    monkeypatch.setattr(ipy, "import_objects", lambda app, registry: {"x": 1})
    monkeypatch.setattr(ipy, "get_ipython_arguments", lambda options=None: ["--quick"])

    runner = get_ipython(app=object(), registry=_DummyRegistry())
    runner()
    assert calls["argv"] == ["--quick"]
    assert calls["ns"] == {"x": 1}


def test_vi_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EDITOR", "/usr/bin/vim")
    assert vi_mode() is True
    monkeypatch.setenv("EDITOR", "/usr/bin/nano")
    assert vi_mode() is False


def test_get_ptpython_runner(monkeypatch: pytest.MonkeyPatch):
    from saffier.cli.operations.shell import ptpython as ptpy

    calls: list[dict[str, object]] = []

    def _embed(**kwargs):
        calls.append(kwargs)

    fake_repl = types.SimpleNamespace(embed=_embed, run_config=object())
    fake_ptpython = types.SimpleNamespace(repl=fake_repl)
    monkeypatch.setitem(__import__("sys").modules, "ptpython", fake_ptpython)
    monkeypatch.setitem(__import__("sys").modules, "ptpython.repl", fake_repl)
    monkeypatch.setattr(ptpy, "import_objects", lambda app, registry: {"y": 2})
    monkeypatch.setattr(ptpy.settings, "ptpython_config_file", "~/.ptpython_missing_config.py")
    monkeypatch.setattr(ptpy.os.path, "exists", lambda path: False)

    runner = get_ptpython(app=object(), registry=_DummyRegistry())
    runner()
    assert calls
    assert calls[0]["globals"] == {"y": 2}


@pytest.mark.anyio
async def test_run_shell_branches(monkeypatch: pytest.MonkeyPatch):
    from saffier.cli.operations.shell import base as shell_base

    events: list[str] = []

    def fake_lifespan(_app):
        class _Ctx:
            async def __aenter__(self):
                events.append("enter")

            async def __aexit__(self, exc_type, exc, tb):
                events.append("exit")

        return _Ctx()

    monkeypatch.setattr(shell_base.nest_asyncio, "apply", lambda: events.append("nest"))
    monkeypatch.setattr(
        shell_base,
        "get_ipython",
        lambda app, registry: lambda: events.append("ipython"),
        raising=False,
    )
    monkeypatch.setattr(
        shell_base,
        "get_ptpython",
        lambda app, registry: lambda: events.append("ptpython"),
        raising=False,
    )

    fake_ipy = types.SimpleNamespace(
        get_ipython=lambda app, registry: lambda: events.append("ipython")
    )
    fake_pt = types.SimpleNamespace(
        get_ptpython=lambda app, registry: lambda: events.append("ptpython")
    )
    monkeypatch.setitem(
        __import__("sys").modules, "saffier.cli.operations.shell.ipython", fake_ipy
    )
    monkeypatch.setitem(
        __import__("sys").modules, "saffier.cli.operations.shell.ptpython", fake_pt
    )

    await run_shell(
        app=object(), lifespan=fake_lifespan, registry=_DummyRegistry(), kernel="ipython"
    )
    await run_shell(
        app=object(), lifespan=fake_lifespan, registry=_DummyRegistry(), kernel="ptpython"
    )
    assert events.count("enter") == 2
    assert "ipython" in events
    assert "ptpython" in events
