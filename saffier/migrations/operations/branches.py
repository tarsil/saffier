"""
Client to interact with Saffier models and migrations.
"""

from typing import Any

import click

from saffier.migrations.base import branches as _branches


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.option("-v", "--verbose", is_flag=True, help="Use more verbose output")
@click.command()
@click.pass_context
def branches(ctx: Any, directory: str, verbose: bool) -> None:
    """Show current branch points"""
    _branches(ctx.obj, directory, verbose)
