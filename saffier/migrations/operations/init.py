"""
Client to interact with Saffier models and migrations.
"""

from typing import Any

import click

from saffier.migrations.base import init as _init


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.option(
    "-t", "--template", default=None, help=('Repository template to use (default is "flask")')
)
@click.option(
    "--package",
    is_flag=True,
    help=("Write empty __init__.py files to the environment and " "version locations"),
)
@click.command(name="init")
@click.pass_context
def init(ctx: Any, directory: str, template: str, package: bool) -> None:
    """Creates a new migration repository."""
    _init(ctx.obj, directory, template, package)
