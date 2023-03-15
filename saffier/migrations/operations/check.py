"""
Client to interact with Saffier models and migrations.
"""

from typing import Any

import click

from saffier.migrations.base import check as _check


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.command()
@click.pass_context
def check(ctx: Any, directory: str) -> None:
    """Check if there are any new operations to migrate"""
    _check(ctx.obj, directory)
