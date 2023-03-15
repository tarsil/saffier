"""
Client to interact with Saffier models and migrations.
"""

from typing import Any

import click

from saffier.migrations.base import stamp as _stamp


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.option(
    "--sql", is_flag=True, help=("Don't emit SQL to database - dump to standard output " "instead")
)
@click.option(
    "--tag", default=None, help=('Arbitrary "tag" name - can be used by custom env.py ' "scripts")
)
@click.argument("revision", default="head")
@click.command()
@click.pass_context
def stamp(ctx: Any, directory: str, sql: bool, tag: str, revision: str) -> None:
    """'stamp' the revision table with the given revision; don't run any
    migrations"""
    _stamp(ctx.obj, directory, revision, sql, tag)
