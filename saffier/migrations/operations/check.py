"""
Client to interact with Saffier models and migrations.
"""

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
def check(ctx, directory):
    """Check if there are any new operations to migrate"""
    _check(ctx.obj, directory)
