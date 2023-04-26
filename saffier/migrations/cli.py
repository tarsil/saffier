"""
Client to interact with Saffier models and migrations.
"""
import inspect
import sys
import typing
from functools import wraps

import click

from saffier.core.terminal import Print
from saffier.exceptions import CommandEnvironmentError
from saffier.migrations.constants import (
    APP_PARAMETER,
    EXCLUDED_COMMANDS,
    HELP_PARAMETER,
    IGNORE_COMMANDS,
)
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
    shell,
    show,
    stamp,
)

printer = Print()


class SaffierGroup(click.Group):
    """Saffier command group with extras for the commands"""

    def add_command(self, cmd: click.Command, name: typing.Optional[str] = None) -> None:
        if cmd.callback:
            cmd.callback = self.wrap_args(cmd.callback)
        return super().add_command(cmd, name)

    def wrap_args(self, func: typing.Any) -> typing.Any:
        params = inspect.signature(func).parameters

        @wraps(func)
        def wrapped(ctx: click.Context, /, *args: typing.Any, **kwargs: typing.Any) -> typing.Any:
            scaffold = ctx.ensure_object(MigrationEnv)
            if "env" in params:
                kwargs["env"] = scaffold
            return func(*args, **kwargs)

        return click.pass_context(wrapped)

    def invoke(self, ctx: click.Context) -> typing.Any:
        """
        Migrations can be ignored depending of the functionality from what is being
        called.
        """
        path = ctx.params.get("path", None)

        # Process any settings
        if HELP_PARAMETER not in sys.argv and not any(
            value in sys.argv for value in EXCLUDED_COMMANDS
        ):
            try:
                migration = MigrationEnv()
                app_env = migration.load_from_env(path=path)
                ctx.obj = app_env
            except CommandEnvironmentError as e:
                if not any(value in sys.argv for value in IGNORE_COMMANDS):
                    printer.write_error(str(e))
                    sys.exit(1)
        return super().invoke(ctx)


@click.group(cls=SaffierGroup)
@click.option(
    APP_PARAMETER,
    "path",
    help="Module path to the application to generate the migrations. In a module:path format.",
)
@click.pass_context
def saffier_cli(ctx: click.Context, path: typing.Optional[str]) -> None:
    """Performs database migrations"""
    ...


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
saffier_cli.add_command(shell, name="shell")
