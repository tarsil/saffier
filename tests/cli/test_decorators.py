import pytest
from alembic.util import CommandError

from saffier.cli.decorators import catch_errors


def test_catch_errors_pass_through():
    called = {"ok": False}

    @catch_errors
    def wrapped():
        called["ok"] = True

    wrapped()
    assert called["ok"] is True


def test_catch_errors_handles_runtime_and_command(monkeypatch):
    monkeypatch.setattr(
        "saffier.cli.decorators.sys.exit", lambda code: (_ for _ in ()).throw(SystemExit(code))
    )

    @catch_errors
    def runtime():
        raise RuntimeError("boom")

    @catch_errors
    def command():
        raise CommandError("bad")

    with pytest.raises(SystemExit):
        runtime()
    with pytest.raises(SystemExit):
        command()
