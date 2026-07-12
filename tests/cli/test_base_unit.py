from __future__ import annotations

import io
import types
from pathlib import Path

import pytest

import saffier
from saffier.cli import base as cli_base
from saffier.conf import override_settings
from saffier.core.signals import post_migrate, pre_migrate
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL


def _make_migrate() -> tuple[cli_base.Migrate, object]:
    database = Database(DATABASE_URL, full_isolation=False)
    registry = saffier.Registry(database=database)
    app = types.SimpleNamespace()
    migrate = cli_base.Migrate(app=app, registry=registry, model_apps={})
    return migrate, app


def test_config_template_directory():
    config = cli_base.Config()
    directory = config.get_template_directory()
    assert directory.endswith("templates")

    custom = cli_base.Config(template_directory="/tmp/custom")
    assert custom.get_template_directory() == "/tmp/custom"


def test_migrate_get_config_and_callbacks():
    migrate, _ = _make_migrate()

    @migrate.configure
    def configure(config):
        config.cmd_opts.custom = True
        return config

    config = migrate.get_config(directory="migrations", arg=["a=1", "b=2"], options=["sql"])
    assert config.cmd_opts.sql is True
    assert config.cmd_opts.custom is True
    assert config.cmd_opts.x == ["a=1", "b=2"]

    scalar = migrate.get_config(directory="migrations", arg="one=1")
    assert scalar.cmd_opts.x == ["one=1"]

    empty = migrate.get_config(directory="migrations", arg=None)
    assert empty.cmd_opts.x is None


def test_migrate_uses_settings_defaults():
    with override_settings(
        migration_directory="project_migrations",
        alembic_ctx_kwargs={"include_schemas": True, "compare_type": False},
    ):
        migrate, _ = _make_migrate()

    assert migrate.directory == "project_migrations"
    assert migrate.alembic_ctx_kwargs["include_schemas"] is True
    assert migrate.alembic_ctx_kwargs["compare_type"] is True
    assert migrate.alembic_ctx_kwargs["render_as_batch"] is True


def test_list_templates_prints_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    template_dir = tmp_path / "templates"
    default = template_dir / "default"
    default.mkdir(parents=True)
    (default / "README").write_text("Default template\nbody\n")
    plain = template_dir / "plain"
    plain.mkdir(parents=True)
    (plain / "README").write_text("Plain template\nbody\n")

    captured = io.StringIO()
    monkeypatch.setattr(cli_base.Config, "get_template_directory", lambda self: str(template_dir))
    monkeypatch.setattr(
        cli_base.Config, "print_stdout", lambda self, text: captured.write(text + "\n")
    )

    cli_base.list_templates()
    output = captured.getvalue()
    assert "default - Default template" in output
    assert "plain - Plain template" in output


def test_init_without_app_uses_settings_directory(monkeypatch: pytest.MonkeyPatch):
    called: dict[str, object] = {}

    monkeypatch.setattr(
        cli_base.command,
        "init",
        lambda config, directory, template, package: called.update(
            {
                "directory": directory,
                "template": template,
                "package": package,
                "config_file_name": config.config_file_name,
            }
        ),
    )

    with override_settings(migration_directory="custom_migrations"):
        cli_base.init(app=None, directory=None, template="plain", package=False)

    assert called["directory"] == "custom_migrations"
    assert str(called["config_file_name"]).endswith("custom_migrations/alembic.ini")


def test_edit_exit_on_old_alembic(monkeypatch: pytest.MonkeyPatch):
    migrate, app = _make_migrate()
    monkeypatch.setattr(cli_base, "alembic_version", (1, 9, 3))

    with pytest.raises(SystemExit):
        cli_base.edit(app=app, directory="migrations", revision="head")

    monkeypatch.setattr(cli_base, "alembic_version", (1, 9, 4))
    called = {}
    monkeypatch.setattr(
        cli_base.command, "edit", lambda config, revision: called.update({"rev": revision})
    )
    cli_base.edit(app=app, directory="migrations", revision="head")
    assert called["rev"] == "head"


def test_revision_dispatches_sender_filtered_migration_signals(
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify revision commands emit migration lifecycle hooks.

    Receivers are connected through the sender-filtered public signal API, then
    the regular synchronous CLI helper is called with Alembic patched out. This
    proves migration hooks run through the command surface rather than a private
    helper alone.
    """
    migrate, app = _make_migrate()
    events: list[tuple[str, str, bool, bool]] = []

    @pre_migrate.connect_via("revision")
    def before_revision(sender, sql, autogenerate, _async_wrapper, **kwargs):
        """Record synchronous pre-revision signal payloads.

        Args:
            sender: Migration command name.
            sql: Whether SQL output mode is active.
            autogenerate: Whether Alembic autogeneration is active.
            _async_wrapper: Synchronous bridge exposed to receivers.
            **kwargs: Additional command metadata.
        """
        events.append(("pre", sender, sql, autogenerate))

    @post_migrate.connect_via("revision")
    async def after_revision(sender, sql, autogenerate, **kwargs):
        """Record asynchronous post-revision signal payloads.

        Args:
            sender: Migration command name.
            sql: Whether SQL output mode is active.
            autogenerate: Whether Alembic autogeneration is active.
            **kwargs: Additional command metadata.
        """
        events.append(("post", sender, sql, autogenerate))

    @pre_migrate.connect_via("upgrade")
    def wrong_sender(sender, **kwargs):
        """Fail if sender filtering routes revision events to upgrade hooks.

        Args:
            sender: Migration command name.
            **kwargs: Additional command metadata.
        """
        raise AssertionError(f"unexpected sender {sender}")

    monkeypatch.setattr(cli_base.command, "revision", lambda *args, **kwargs: None)
    try:
        cli_base.revision(
            app=app,
            directory="migrations",
            message="hooked",
            autogenerate=True,
            sql=True,
        )
    finally:
        pre_migrate.disconnect(before_revision)
        post_migrate.disconnect(after_revision)
        pre_migrate.disconnect(wrong_sender)

    assert events == [
        ("pre", "revision", True, True),
        ("post", "revision", True, True),
    ]


def test_upgrade_and_downgrade_dispatch_success_only_migration_signals(
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify upgrade/downgrade hooks fire only around successful commands.

    The command functions should emit pre hooks before Alembic, emit post hooks
    after success, and avoid post hooks when Alembic raises. That distinction is
    important for receivers that mutate data after a migration completes.
    """
    migrate, app = _make_migrate()
    del migrate
    events: list[tuple[str, str]] = []

    @pre_migrate.connect_via("upgrade")
    def before_upgrade(sender, **kwargs):
        """Record pre-upgrade signal dispatch.

        Args:
            sender: Migration command name.
            **kwargs: Additional command metadata.
        """
        events.append(("pre", sender))

    @post_migrate.connect_via("upgrade")
    def after_upgrade(sender, **kwargs):
        """Record post-upgrade signal dispatch.

        Args:
            sender: Migration command name.
            **kwargs: Additional command metadata.
        """
        events.append(("post", sender))

    @pre_migrate.connect_via("downgrade")
    def before_downgrade(sender, revision, **kwargs):
        """Record downgrade signal dispatch and normalized SQL revision.

        Args:
            sender: Migration command name.
            revision: Alembic revision passed to the command.
            **kwargs: Additional command metadata.
        """
        events.append(("pre", f"{sender}:{revision}"))

    @post_migrate.connect_via("downgrade")
    def after_downgrade(sender, **kwargs):
        """Fail if a failed downgrade emits a post hook.

        Args:
            sender: Migration command name.
            **kwargs: Additional command metadata.
        """
        raise AssertionError(f"unexpected post sender {sender}")

    monkeypatch.setattr(cli_base.command, "upgrade", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        cli_base.command,
        "downgrade",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom")),
    )
    try:
        cli_base.upgrade(app=app, directory="migrations", revision="head")
        with pytest.raises(ValueError):
            cli_base.downgrade(app=app, directory="migrations", revision="-1", sql=True)
    finally:
        pre_migrate.disconnect(before_upgrade)
        post_migrate.disconnect(after_upgrade)
        pre_migrate.disconnect(before_downgrade)
        post_migrate.disconnect(after_downgrade)

    assert events == [
        ("pre", "upgrade"),
        ("post", "upgrade"),
        ("pre", "downgrade:head:-1"),
    ]
