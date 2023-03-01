import argparse
import os
import typing
from typing import Optional

from alembic import __version__ as __alembic_version__
from alembic import command
from alembic.config import Config as AlembicConfig

from saffier import Registry
from saffier.migrations.constants import DEFAULT_TEMPLATE_NAME
from saffier.migrations.decorators import catch_errors
from saffier.types import DictAny

alembic_version = tuple([int(v) for v in __alembic_version__.split(".")[0:3]])
object_setattr = object.__setattr__


class MigrateConfig:
    def __init__(self, migrate: typing.Any, registry: Registry, **kwargs):
        self.migrate = migrate
        self.registry = registry
        self.directory = migrate.directory
        self.kwargs = kwargs

    @property
    def metadata(self):
        return self.registry.metadata


class Config(AlembicConfig):
    """
    Base configuration connecting Saffier with Alembic.
    """

    def __init__(self, *args, **kwargs):
        self.template_directory = kwargs.pop("template_directory", None)
        super().__init__(*args, **kwargs)

    def get_template_directory(self) -> str:
        if self.template_directory:
            return self.template_directory
        package_dir = os.path.abspath(os.path.dirname(__file__))
        return os.path.join(package_dir, "templates")


class Migrate:
    """
    Main migration object that should be used in any application
    that requires Saffier to control the migration process.

    This process will always create an entry in any ASGI application
    if there isn't any.
    """

    def __init__(
        self,
        app: typing.Any,
        registry: Registry,
        directory: str = "migrations",
        compare_type: bool = True,
        render_as_batch: bool = True,
        **kwargs: DictAny,
    ):
        assert isinstance(registry, Registry), "Registry must be an instance of saffier.Registry"

        self.app = app
        self.configure_callbacks = []
        self.registry = registry
        self.directory = str(directory)
        self.alembic_ctx_kwargs = kwargs
        self.alembic_ctx_kwargs["compare_type"] = compare_type
        self.alembic_ctx_kwargs["render_as_batch"] = render_as_batch

        self.set_saffier_extension(app)

    def set_saffier_extension(self, app):
        """
        Sets a saffier dictionary for the app object.
        """
        migrate = MigrateConfig(self, self.registry, **self.alembic_ctx_kwargs)
        object_setattr(app, "_saffier_db", {})
        app._saffier_db["migrate"] = migrate

    def configure(self, f):
        self.configure_callbacks.append(f)
        return f

    def call_configure_callbacks(self, config):
        for f in self.configure_callbacks:
            config = f(config)
        return config

    def get_config(
        self,
        directory: Optional[str] = None,
        arg: Optional[typing.Any] = None,
        options: Optional[typing.Any] = None,
    ):
        if directory is None:
            directory = self.directory
        directory = str(directory)
        config = Config(os.path.join(directory, "alembic.ini"))
        config.set_main_option("script_location", directory)

        if config.cmd_opts is None:
            config.cmd_opts = argparse.Namespace()

        for option in options or []:
            setattr(config.cmd_opts, option, True)

        if not hasattr(config.cmd_opts, "x"):
            if arg is not None:
                setattr(config.cmd_opts, "x", [])
                if isinstance(arg, list) or isinstance(arg, tuple):
                    for x in arg:
                        config.cmd_opts.x.append(x)
                else:
                    config.cmd_opts.x.append(arg)
            else:
                setattr(config.cmd_opts, "x", None)
        return self.call_configure_callbacks(config)


@catch_errors
def list_templates():
    """Lists the available templates"""
    config = Config()
    config.print_stdout("Available templates:\n")

    for name in sorted(os.listdir(config.get_template_directory())):
        with open(os.path.join(config.get_template_directory(), name, "README")) as readme:
            synopsis = next(readme).strip()
        config.print_stdout(f"{name} - {synopsis}")


@catch_errors
def init(
    app: Optional[typing.Any],
    directory: Optional[str] = None,
    multidb: bool = False,
    template: Optional[str] = None,
    package: bool = False,
):
    """Creates a new migration folder"""
    if directory is None:
        directory = "migrations"

    template_directory = None

    if template is not None and ("/" in template or "\\" in template):
        template_directory, template = os.path.split(template)

    config = Config(template_directory=template_directory)
    config.set_main_option("script_location", directory)
    config.config_file_name = os.path.join(directory, "alembic.ini")
    config = app._saffier_db["migrate"].migrate.call_configure_callbacks(config)

    if template is None:
        template = DEFAULT_TEMPLATE_NAME
    command.init(config, directory, template, package)


@catch_errors
def revision(
    app: Optional[typing.Any],
    directory: Optional[str] = None,
    message: Optional[str] = None,
    autogenerate: bool = False,
    sql: bool = False,
    head: Optional[str] = "head",
    splice: bool = False,
    branch_label: Optional[str] = None,
    version_path: Optional[str] = None,
    revision_id: Optional[typing.Any] = None,
):
    """
    Creates a new revision file
    """
    options = ["autogenerate"] if autogenerate else None
    config = app._saffier_db["migrate"].migrate.get_config(directory, options)

    command.revision(
        config,
        message,
        autogenerate=autogenerate,
        sql=sql,
        head=head,
        splice=splice,
        branch_label=branch_label,
        version_path=version_path,
        rev_id=revision_id,
    )


@catch_errors
def migrate(
    app: Optional[typing.Any],
    directory: Optional[str] = None,
    message: Optional[str] = None,
    sql: bool = False,
    head: Optional[str] = "head",
    splice: bool = False,
    branch_label: Optional[str] = None,
    version_path: Optional[str] = None,
    revision_id: Optional[typing.Any] = None,
    arg: Optional[typing.Any] = None,
):
    """Alias for 'revision --autogenerate'"""
    config = app._saffier_db["migrate"].migrate.get_config(
        directory, options=["autogenerate"], arg=arg
    )

    command.revision(
        config,
        message,
        autogenerate=True,
        sql=sql,
        head=head,
        splice=splice,
        branch_label=branch_label,
        version_path=version_path,
        rev_id=revision_id,
    )


@catch_errors
def edit(
    app: Optional[typing.Any], directory: Optional[str] = None, revision: Optional[str] = "current"
):
    """Edit current revision."""
    if alembic_version >= (1, 9, 4):
        config = app._saffier_db["migrate"].migrate.get_config(directory)
        command.edit(config, revision)
    else:
        raise RuntimeError("Alembic 1.9.4 or greater is required")


@catch_errors
def merge(
    app: Optional[typing.Any],
    directory: Optional[str] = None,
    revisions: Optional[str] = "",
    message: Optional[str] = None,
    branch_label: Optional[str] = None,
    revision_id: Optional[str] = None,
):
    """Merge two revisions together.  Creates a new migration file"""
    config = app._saffier_db["migrate"].migrate.get_config(directory)
    command.merge(
        config, revisions, message=message, branch_label=branch_label, rev_id=revision_id
    )


@catch_errors
def upgrade(
    app: Optional[typing.Any],
    directory: Optional[str] = None,
    revision: Optional[str] = "head",
    sql: bool = False,
    tag: bool = None,
    arg: Optional[typing.Any] = None,
):
    """Upgrade to a later version"""
    config = app._saffier_db["migrate"].migrate.get_config(directory, arg=arg)
    command.upgrade(config, revision, sql=sql, tag=tag)


@catch_errors
def downgrade(
    app: Optional[typing.Any],
    directory: Optional[str] = None,
    revision: Optional[str] = "-1",
    sql: bool = False,
    tag: bool = None,
    arg: Optional[typing.Any] = None,
):
    """Revert to a previous version"""
    config = app._saffier_db["migrate"].migrate.get_config(directory, arg=arg)
    if sql and revision == "-1":
        revision = "head:-1"
    command.downgrade(config, revision, sql=sql, tag=tag)


@catch_errors
def show(
    app: Optional[typing.Any],
    directory: Optional[str] = None,
    revision: Optional[str] = "head",
):
    """Show the revision denoted by the given symbol."""
    config = app._saffier_db["migrate"].migrate.get_config(directory)
    command.show(config, revision)


@catch_errors
def history(
    app: Optional[typing.Any],
    directory: Optional[str] = None,
    rev_range: Optional[typing.Any] = None,
    verbose: bool = False,
    indicate_current: bool = False,
):
    """List changeset scripts in chronological order."""
    config = app._saffier_db["migrate"].migrate.get_config(directory)
    command.history(config, rev_range, verbose=verbose, indicate_current=indicate_current)


@catch_errors
def heads(
    app: Optional[typing.Any],
    directory: Optional[str] = None,
    verbose: bool = False,
    resolve_dependencies: bool = False,
):
    """Show current available heads in the script directory"""
    config = app._saffier_db["migrate"].migrate.get_config(directory)
    command.heads(config, verbose=verbose, resolve_dependencies=resolve_dependencies)


@catch_errors
def branches(app: Optional[typing.Any], directory: Optional[str] = None, verbose: bool = False):
    """Show current branch points"""
    config = app._saffier_db["migrate"].migrate.get_config(directory)
    command.branches(config, verbose=verbose)


@catch_errors
def current(app: Optional[typing.Any], directory: Optional[str] = None, verbose: bool = False):
    """Display the current revision for each database."""
    config = app._saffier_db["migrate"].migrate.get_config(directory)
    command.current(config, verbose=verbose)


@catch_errors
def stamp(
    app: Optional[typing.Any],
    directory: Optional[str] = None,
    revision: Optional[str] = "head",
    sql: bool = False,
    tag: Optional[typing.Any] = None,
):
    """'stamp' the revision table with the given revision; don't run any
    migrations"""
    config = app._saffier_db["migrate"].migrate.get_config(directory)
    command.stamp(config, revision, sql=sql, tag=tag)


@catch_errors
def check(
    app: Optional[typing.Any],
    directory: Optional[str] = None,
):
    """Check if there are any new operations to migrate"""
    config = app._saffier_db["migrate"].migrate.get_config(directory)
    command.check(config)
