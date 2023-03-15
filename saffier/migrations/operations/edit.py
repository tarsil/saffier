"""
Client to interact with Saffier models and migrations.
"""

from typing import Any

import click

from saffier.migrations.base import edit as _edit


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.command()
@click.argument("revision", default="head")
@click.pass_context
def edit(ctx: Any, directory: str, revision: str) -> None:
    """Edit a revision file"""
    _edit(ctx.obj, directory, revision)
