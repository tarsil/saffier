"""
Client to interact with Saffier models and migrations.
"""

import click

from saffier.migrations.base import current as _current


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.option("-v", "--verbose", is_flag=True, help="Use more verbose output")
@click.command()
@click.pass_context
def current(ctx, directory, verbose):
    """Display the current revision for each database."""
    _current(ctx.obj, directory, verbose)
