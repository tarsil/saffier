"""
Client to interact with Saffier models and migrations.
"""

from typing import Any

import click

from saffier.migrations.base import heads as _heads


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.option("-v", "--verbose", is_flag=True, help="Use more verbose output")
@click.option(
    "--resolve-dependencies", is_flag=True, help="Treat dependency versions as down revisions"
)
@click.command()
@click.pass_context
def heads(ctx: Any, directory: str, verbose: bool, resolve_dependencies: bool) -> None:
    """Show current available heads in the script directory"""
    _heads(ctx.obj, directory, verbose, resolve_dependencies)
