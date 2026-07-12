from __future__ import annotations

import types
from importlib import import_module

admin_serve_module = import_module("saffier.cli.operations.admin_serve")
admin_serve = admin_serve_module.admin_serve


class _Registry:
    """Small registry stand-in used by the admin CLI unit tests.

    The real CLI receives a Saffier registry from migration discovery. The unit
    tests only need the ``create_all`` coroutine so the command can exercise its
    startup branch without touching a real database.
    """

    async def create_all(self):
        """Pretend to create database tables for the CLI startup path.

        Returning ``None`` is enough for the command callback because the test
        patches ``saffier.run_sync`` and only verifies that the coroutine is
        scheduled when ``--create-all`` is requested.
        """
        return None


def _make_app():
    """Build a minimal migration application and registry pair.

    The command discovers the application through Saffier's migration helpers.
    Supplying the same shape here lets the test focus on admin server assembly,
    not the migration discovery machinery.
    """
    registry = _Registry()
    migrate = types.SimpleNamespace(registry=registry)
    return types.SimpleNamespace(_saffier_db={"migrate": migrate}), registry


def test_admin_serve_builds_and_runs(monkeypatch):
    """Verify that ``admin_serve`` assembles a Lilya admin server.

    The test patches discovery, admin app creation, table creation, and Palfrey
    execution so the command callback can run entirely in process. It then
    checks that user-provided authentication, host, port, log level, and default
    admin prefix values reach the correct integration points.
    """
    app, registry = _make_app()
    palfrey_calls = {}
    admin_calls = {}

    async def admin_app(scope, receive, send):
        """Act as the mounted admin ASGI application returned by the factory.

        Lilya accepts this callable as a real ASGI endpoint, which keeps the
        command test faithful to production wiring while avoiding a dependency
        on the full admin router internals.
        """
        return None

    monkeypatch.setattr(admin_serve_module, "get_migration_app", lambda: app)
    monkeypatch.setattr(admin_serve_module, "get_migration_registry", lambda: registry)
    monkeypatch.setattr(
        admin_serve_module,
        "create_admin_app",
        lambda **kwargs: admin_calls.update(kwargs) or admin_app,
    )
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
        admin_prefix_url=None,
    )

    assert palfrey_calls["host"] == "127.0.0.1"
    assert palfrey_calls["port"] == 8010
    assert palfrey_calls["log_level"] == "debug"
    assert palfrey_calls["config_or_app"] is not None
    assert admin_calls["config"].admin_prefix_url == "/admin"
    assert admin_calls["auth_username"] == "root"
    assert admin_calls["auth_password"] == "secret"


def test_admin_serve_auto_generates_password(monkeypatch, capsys):
    """Verify password generation and explicit public admin prefix handling.

    When no password is supplied, the command should generate one, print it for
    the operator, and pass it into the admin app factory. The same invocation
    also proves that ``--admin-prefix-url`` overrides the internal mount path
    for reverse-proxy-aware links and redirects.
    """
    app, registry = _make_app()
    admin_calls = {}

    async def admin_app(scope, receive, send):
        """Act as the mounted admin ASGI application returned by the factory.

        The command only needs a valid ASGI callable to construct the Lilya
        include, so this stub records no state and performs no response IO.
        """
        return None

    monkeypatch.setattr(admin_serve_module, "get_migration_app", lambda: app)
    monkeypatch.setattr(admin_serve_module, "get_migration_registry", lambda: registry)
    monkeypatch.setattr(
        admin_serve_module,
        "create_admin_app",
        lambda **kwargs: admin_calls.update(kwargs) or admin_app,
    )
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
        admin_prefix_url="/public/admin",
    )
    output = capsys.readouterr().out
    assert "Saffier admin password: token" in output
    assert admin_calls["config"].admin_prefix_url == "/public/admin"
    assert admin_calls["auth_password"] == "token"
