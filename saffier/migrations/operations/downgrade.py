"""
Client to interact with Saffier models and migrations.
"""

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
def downgrade(ctx, directory, sql, tag, arg, revision):
    """Revert to a previous version"""
    _downgrade(ctx.obj, directory, revision, sql, tag, arg)
