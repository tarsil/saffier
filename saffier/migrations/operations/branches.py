"""
Client to interact with Saffier models and migrations.
"""


import click

from saffier.migrations.base import branches as _branches
from saffier.migrations.env import MigrationEnv


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.option("-v", "--verbose", is_flag=True, help="Use more verbose output")
@click.command()
def branches(env: MigrationEnv, directory: str, verbose: bool) -> None:
    """Show current branch points"""
    _branches(env.app, directory, verbose)
