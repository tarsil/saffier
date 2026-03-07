from __future__ import annotations

import types
from importlib import import_module

admin_serve_module = import_module("saffier.cli.operations.admin_serve")
admin_serve = admin_serve_module.admin_serve


class _Registry:
    async def create_all(self):
        return None


def _make_app():
    registry = _Registry()
    migrate = types.SimpleNamespace(registry=registry)
    return types.SimpleNamespace(_saffier_db={"migrate": migrate}), registry


def test_admin_serve_builds_and_runs(monkeypatch):
    app, registry = _make_app()
    palfrey_calls = {}

    monkeypatch.setattr(admin_serve_module, "get_migration_app", lambda: app)
    monkeypatch.setattr(admin_serve_module, "create_admin_app", lambda **kwargs: "admin-app")
    monkeypatch.setattr(admin_serve_module.saffier, "run_sync", lambda coro: coro.close())
    monkeypatch.setitem(
        __import__("sys").modules,
        "palfrey",
        types.SimpleNamespace(run=lambda **kwargs: palfrey_calls.update(kwargs)),
    )

    ctx = types.SimpleNamespace(command=types.SimpleNamespace(params=[]))
    admin_serve.callback.__wrapped__(
        ctx,
        port=8010,
        host="127.0.0.1",
        debug=True,
        create_all=True,
        log_level="debug",
        auth_name="root",
        auth_pw="secret",
        admin_path="/admin",
    )

    assert palfrey_calls["host"] == "127.0.0.1"
    assert palfrey_calls["port"] == 8010
    assert palfrey_calls["log_level"] == "debug"
    assert palfrey_calls["config_or_app"] is not None


def test_admin_serve_auto_generates_password(monkeypatch, capsys):
    app, _ = _make_app()

    monkeypatch.setattr(admin_serve_module, "get_migration_app", lambda: app)
    monkeypatch.setattr(admin_serve_module, "create_admin_app", lambda **kwargs: "admin")
    monkeypatch.setitem(
        __import__("sys").modules,
        "palfrey",
        types.SimpleNamespace(run=lambda **kwargs: None),
    )
    monkeypatch.setattr(admin_serve_module.secrets, "token_urlsafe", lambda n: "token")

    ctx = types.SimpleNamespace(command=types.SimpleNamespace(params=[]))
    admin_serve.callback.__wrapped__(
        ctx,
        port=8000,
        host="localhost",
        debug=False,
        create_all=False,
        log_level="info",
        auth_name="admin",
        auth_pw=None,
        admin_path="/admin",
    )
    output = capsys.readouterr().out
    assert "Saffier admin password: token" in output
