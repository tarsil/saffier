"""
Client to interact with Saffier models and migrations.
"""

from __future__ import annotations

import sys
import typing

import click
from sayer import Sayer, error
from sayer.params import Option

import saffier
from saffier.cli.constants import (
    EXCLUDED_COMMANDS,
    HELP_PARAMETER,
    IGNORE_COMMANDS,
    SAFFIER_DISCOVER_APP,
)
from saffier.cli.env import MigrationEnv
from saffier.cli.operations import (
    check,
    current,
    downgrade,
    edit,
    heads,
    history,
    init,
    inspect_db,
    list_templates,
    makemigrations,
    merge,
    migrate,
    revision,
    shell,
    show,
    stamp,
)
from saffier.cli.state import clear_migration_env, set_migration_env
from saffier.exceptions import CommandEnvironmentError

help_text = """
Saffier command line tool allowing to run Saffier native directives.

How to run Saffier native: `saffier init`. Or any other Saffier native command.

    Example: `saffier shell`
"""

saffier_cli = Sayer(
    name="saffier",
    help=help_text,
    add_version_option=True,
    version=saffier.__version__,
)


@saffier_cli.callback(invoke_without_command=True)
def saffier_callback(
    ctx: click.Context,
    app: typing.Annotated[
        str | None,
        Option(
            None,
            help=(
                "Module path to the application to generate the migrations. "
                "In a module:path format."
            ),
            envvar=SAFFIER_DISCOVER_APP,
        ),
    ],
) -> None:
    """Perform database migration directives."""
    if HELP_PARAMETER in sys.argv:
        return

    if any(value in sys.argv for value in EXCLUDED_COMMANDS):
        clear_migration_env()
        return

    try:
        migration = MigrationEnv()
        app_env = migration.load_from_env(path=app)
        set_migration_env(app_env)
        ctx.obj = app_env
    except CommandEnvironmentError as exc:
        if not any(value in sys.argv for value in IGNORE_COMMANDS):
            error(str(exc))
            sys.exit(1)


def _add_command(command: click.Command, name: str | None = None) -> None:
    saffier_cli.add_command(command, name=name)


_add_command(list_templates)
_add_command(init, name="init")
_add_command(revision, name="revision")
_add_command(makemigrations, name="makemigrations")
_add_command(edit, name="edit")
_add_command(merge, name="merge")
_add_command(migrate, name="migrate")
_add_command(downgrade, name="downgrade")
_add_command(show, name="show")
_add_command(history, name="history")
_add_command(heads, name="heads")
_add_command(current, name="current")
_add_command(stamp, name="stamp")
_add_command(check, name="check")
_add_command(shell, name="shell")
_add_command(inspect_db, name="inspectdb")
