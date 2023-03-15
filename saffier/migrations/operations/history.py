"""
Client to interact with Saffier models and migrations.
"""

from typing import Any

import click

from saffier.migrations.base import history as _history


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.option(
    "-r", "--rev-range", default=None, help="Specify a revision range; format is [start]:[end]"
)
@click.option("-v", "--verbose", is_flag=True, help="Use more verbose output")
@click.option(
    "-i",
    "--indicate-current",
    is_flag=True,
    help=("Indicate current version (Alembic 0.9.9 or greater is " "required)"),
)
@click.command()
@click.pass_context
def history(
    ctx: Any, directory: str, rev_range: str, verbose: bool, indicate_current: bool
) -> None:
    """List changeset scripts in chronological order."""
    _history(ctx.obj, directory, rev_range, verbose, indicate_current)
