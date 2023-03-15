"""
Client to interact with Saffier models and migrations.
"""

from typing import Any

import click

from saffier.migrations.base import downgrade as _downgrade


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
@click.option(
    "-x", "--arg", multiple=True, help="Additional arguments consumed by custom env.py scripts"
)
@click.command()
@click.argument("revision", default="-1")
@click.pass_context
def downgrade(ctx: Any, directory: str, sql: bool, tag: str, arg: Any, revision: str) -> None:
    """Revert to a previous version"""
    _downgrade(ctx.obj, directory, revision, sql, tag, arg)
