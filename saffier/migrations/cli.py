"""
Client to interact with Saffier models and migrations.
"""
import typing

import click

from saffier.migrations.base import branches as _branches
from saffier.migrations.base import check as _check
from saffier.migrations.base import current as _current
from saffier.migrations.base import downgrade as _downgrade
from saffier.migrations.base import edit as _edit
from saffier.migrations.base import heads as _heads
from saffier.migrations.base import history as _history
from saffier.migrations.base import init as _init
from saffier.migrations.base import list_templates as template_list
from saffier.migrations.base import merge as _merge
from saffier.migrations.base import migrate as _migrate
from saffier.migrations.base import revision as _revision
from saffier.migrations.base import show as _show
from saffier.migrations.base import stamp as _stamp
from saffier.migrations.base import upgrade as _upgrade
from saffier.migrations.constants import APP_PARAMETER
from saffier.migrations.env import MigrationEnv


@click.group()
@click.option(
    APP_PARAMETER,
    "path",
    help="Module path to the application to generate the migrations. In a module:path format.",
)
@click.pass_context
def saffier_cli(ctx: click.Context, path: typing.Optional[str]):
    """Performs database migrations"""
    migration = MigrationEnv()
    app_env = migration.load_from_env(path=path)
    ctx.obj = app_env.app


@saffier_cli.command()
def list_templates():
    template_list()


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.option("--multidb", is_flag=True, help=("Support multiple databases"))
@click.option(
    "-t", "--template", default=None, help=('Repository template to use (default is "flask")')
)
@click.option(
    "--package",
    is_flag=True,
    help=("Write empty __init__.py files to the environment and " "version locations"),
)
@saffier_cli.command()
@click.pass_context
def init(ctx, directory, multidb, template, package):
    """Creates a new migration repository."""
    _init(ctx.obj, directory, multidb, template, package)


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.option("-m", "--message", default=None, help="Revision message")
@click.option(
    "--autogenerate",
    is_flag=True,
    help=(
        "Populate revision script with candidate migration "
        "operations, based on comparison of database to model"
    ),
)
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
@saffier_cli.command()
@click.pass_context
def revision(
    ctx, directory, message, autogenerate, sql, head, splice, branch_label, version_path, rev_id
):
    """Create a new revision file."""
    _revision(
        ctx.obj,
        directory,
        message,
        autogenerate,
        sql,
        head,
        splice,
        branch_label,
        version_path,
        rev_id,
    )


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
@saffier_cli.command()
@click.pass_context
def makemigrations(
    ctx, directory, message, sql, head, splice, branch_label, version_path, rev_id, arg
):
    """Autogenerate a new revision file (Alias for
    'revision --autogenerate')"""
    _migrate(
        ctx.obj, directory, message, sql, head, splice, branch_label, version_path, rev_id, arg
    )


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@saffier_cli.command()
@click.argument("revision", default="head")
@click.pass_context
def edit(ctx, directory, revision):
    """Edit a revision file"""
    _edit(ctx.obj, directory, revision)


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
@saffier_cli.command()
@click.argument("revisions", nargs=-1)
@click.pass_context
def merge(ctx, directory, message, branch_label, rev_id, revisions):
    """Merge two revisions together, creating a new revision file"""
    _merge(ctx.obj, directory, revisions, message, branch_label, rev_id)


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
@saffier_cli.command()
@click.argument("revision", default="head")
@click.pass_context
def migrate(ctx, directory, sql, tag, arg, revision):
    """
    Upgrades to the latest version or to a specific version
    provided by the --tag.
    """
    _upgrade(ctx.obj, directory, revision, sql, tag, arg)


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
@saffier_cli.command()
@click.argument("revision", default="-1")
@click.pass_context
def downgrade(ctx, directory, sql, tag, arg, revision):
    """Revert to a previous version"""
    _downgrade(ctx.obj, directory, revision, sql, tag, arg)


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@saffier_cli.command()
@click.argument("revision", default="head")
@click.pass_context
def show(ctx, directory, revision):
    """Show the revision denoted by the given symbol."""
    _show(ctx.obj, directory, revision)


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.option(
    "-r", "--rev-range", default=None, help="Specify a revision range; format is [start]:[end]"
)
@click.option("-v", "--verbose", is_flag=True, help="Use more verbose output")
@click.option(
    "-i",
    "--indicate-current",
    is_flag=True,
    help=("Indicate current version (Alembic 0.9.9 or greater is " "required)"),
)
@saffier_cli.command()
@click.pass_context
def history(ctx, directory, rev_range, verbose, indicate_current):
    """List changeset scripts in chronological order."""
    _history(ctx.obj, directory, rev_range, verbose, indicate_current)


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.option("-v", "--verbose", is_flag=True, help="Use more verbose output")
@click.option(
    "--resolve-dependencies", is_flag=True, help="Treat dependency versions as down revisions"
)
@saffier_cli.command()
@click.pass_context
def heads(ctx, directory, verbose, resolve_dependencies):
    """Show current available heads in the script directory"""
    _heads(ctx.obj, directory, verbose, resolve_dependencies)


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.option("-v", "--verbose", is_flag=True, help="Use more verbose output")
@saffier_cli.command()
@click.pass_context
def branches(ctx, directory, verbose):
    """Show current branch points"""
    _branches(ctx.obj, directory, verbose)


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@click.option("-v", "--verbose", is_flag=True, help="Use more verbose output")
@saffier_cli.command()
@click.pass_context
def current(ctx, directory, verbose):
    """Display the current revision for each database."""
    _current(ctx.obj, directory, verbose)


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
@saffier_cli.command()
@click.pass_context
def stamp(ctx, directory, sql, tag, revision):
    """'stamp' the revision table with the given revision; don't run any
    migrations"""
    _stamp(ctx.obj, directory, revision, sql, tag)


@click.option(
    "-d",
    "--directory",
    default=None,
    help=('Migration script directory (default is "migrations")'),
)
@saffier_cli.command()
@click.pass_context
def check(ctx, directory):
    """Check if there are any new operations to migrate"""
    _check(ctx.obj, directory)


saffier_cli.add_command(list_templates, name="list-templates")
saffier_cli.add_command(init, name="init")
saffier_cli.add_command(revision, name="revision")
saffier_cli.add_command(makemigrations, name="makemigrations")
saffier_cli.add_command(edit, name="edit")
saffier_cli.add_command(merge, name="merge")
saffier_cli.add_command(migrate, name="migrate")
saffier_cli.add_command(downgrade, name="downgrade")
saffier_cli.add_command(show, name="show")
saffier_cli.add_command(history, name="history")
saffier_cli.add_command(heads, name="heads")
saffier_cli.add_command(current, name="current")
saffier_cli.add_command(stamp, name="stamp")
saffier_cli.add_command(check, name="check")
