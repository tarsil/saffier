from __future__ import annotations

import io
import types
from pathlib import Path

import pytest

import saffier
from saffier.cli import base as cli_base
from saffier.conf import override_settings
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
