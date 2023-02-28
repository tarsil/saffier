"""
Client to interact with Saffier models and migrations.
"""

import click

from saffier.migrations.base import show as _show


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.command()
@click.argument("revision", default="head")
@click.pass_context
def show(ctx, directory, revision):
    """Show the revision denoted by the given symbol."""
    _show(ctx.obj, directory, revision)
