import click

from saffier.migrations.base import edit as _edit
from saffier.migrations.env import MigrationEnv


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.command()
@click.argument("revision", default="head")
def edit(env: MigrationEnv, directory: str, revision: str) -> None:
    """Edit a revision file"""
    _edit(env.app, directory, revision)
