"""
Client to interact with Saffier models and migrations.
"""
import sys
import typing

import click

from saffier.migrations.constants import APP_PARAMETER, HELP_PARAMETER
from saffier.migrations.env import MigrationEnv
from saffier.migrations.operations import (
    check,
    current,
    downgrade,
    edit,
    heads,
    history,
    init,
    list_templates,
    makemigrations,
    merge,
    migrate,
    revision,
    show,
    stamp,
)


@click.group()
@click.option(
    APP_PARAMETER,
    "path",
    help="Module path to the application to generate the migrations. In a module:path format.",
)
@click.pass_context
def saffier_cli(ctx: click.Context, path: typing.Optional[str]) -> None:
    """Performs database migrations"""
    if HELP_PARAMETER not in sys.argv:
        migration = MigrationEnv()
        app_env = migration.load_from_env(path=path)
        ctx.obj = app_env.app


saffier_cli.add_command(list_templates)
saffier_cli.add_command(init, name="init")
saffier_cli.add_command(revision, name="revision")
saffier_cli.add_command(makemigrations, name="makemigrations")
saffier_cli.add_command(edit, name="edit")
saffier_cli.add_command(merge, name="merge")
saffier_cli.add_command(migrate, name="migrate")
saffier_cli.add_command(downgrade, name="downgrade")
saffier_cli.add_command(show, name="show")
saffier_cli.add_command(history, name="history")
saffier_cli.add_command(heads, name="heads")
saffier_cli.add_command(current, name="current")
saffier_cli.add_command(stamp, name="stamp")
saffier_cli.add_command(check, name="check")
