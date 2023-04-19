import click

from saffier.migrations.base import show as _show
from saffier.migrations.env import MigrationEnv


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.command()
@click.argument("revision", default="head")
def show(env: MigrationEnv, directory: str, revision: str) -> None:
    """Show the revision denoted by the given symbol."""
    _show(env.app, directory, revision)
