"""
Client to interact with Saffier models and migrations.
"""

import click

from saffier.migrations.base import migrate as _migrate


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.option("-m", "--message", default=None, help="Revision message")
@click.option(
    "--sql", is_flag=True, help=("Don't emit SQL to database - dump to standard output " "instead")
)
@click.option(
    "--head",
    default="head",
    help=("Specify head revision or <branchname>@head to base new " "revision on"),
)
@click.option(
    "--splice", is_flag=True, help=('Allow a non-head revision as the "head" to splice onto')
)
@click.option(
    "--branch-label", default=None, help=("Specify a branch label to apply to the new revision")
)
@click.option(
    "--version-path", default=None, help=("Specify specific path from config for version file")
)
@click.option(
    "--rev-id", default=None, help=("Specify a hardcoded revision id instead of generating " "one")
)
@click.option(
    "-x", "--arg", multiple=True, help="Additional arguments consumed by custom env.py scripts"
)
@click.command()
@click.pass_context
def makemigrations(
    ctx, directory, message, sql, head, splice, branch_label, version_path, rev_id, arg
):
    """Autogenerate a new revision file (Alias for
    'revision --autogenerate')"""
    _migrate(
        ctx.obj, directory, message, sql, head, splice, branch_label, version_path, rev_id, arg
    )
