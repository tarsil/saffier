"""
Client to interact with Saffier models and migrations.
"""

import click

from saffier.migrations.base import merge as _merge


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.option("-m", "--message", default=None, help="Merge revision message")
@click.option(
    "--branch-label", default=None, help=("Specify a branch label to apply to the new revision")
)
@click.option(
    "--rev-id", default=None, help=("Specify a hardcoded revision id instead of generating " "one")
)
@click.command()
@click.argument("revisions", nargs=-1)
@click.pass_context
def merge(ctx, directory, message, branch_label, rev_id, revisions):
    """Merge two revisions together, creating a new revision file"""
    _merge(ctx.obj, directory, revisions, message, branch_label, rev_id)
