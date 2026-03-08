import argparse
import inspect
import os
import typing
import warnings
from collections.abc import Callable
from importlib import import_module
from typing import TYPE_CHECKING, Any, cast

from alembic import __version__ as __alembic_version__
from alembic import command
from alembic.config import Config as AlembicConfig

from saffier._instance import Instance, get_active_instance
from saffier.cli.constants import DEFAULT_TEMPLATE_NAME, SAFFIER_DB
from saffier.cli.decorators import catch_errors
from saffier.conf import _monkay, settings
from saffier.core.extras.base import BaseExtra
from saffier.utils.compat import is_class_and_subclass

if TYPE_CHECKING:
    from saffier.core.connection.registry import Registry

alembic_version = tuple(int(v) for v in __alembic_version__.split(".")[0:3])
object_setattr = object.__setattr__


class MigrateConfig:
    def __init__(self, migrate: typing.Any, registry: "Registry", **kwargs: Any) -> None:
        self.migrate = migrate
        self.registry = registry
        self.directory = migrate.directory
        self.kwargs = kwargs

    @property
    def metadata(self) -> typing.Any:
        return self.registry.metadata


class Config(AlembicConfig):
    """Alembic configuration wrapper used by Saffier's migration commands.

    The wrapper adds Saffier-specific template lookup and centralizes the logic
    that prepares Alembic command options from CLI arguments and active app
    discovery state.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.template_directory = kwargs.pop("template_directory", None)
        super().__init__(*args, **kwargs)

    def get_template_directory(self) -> Any:
        if self.template_directory:
            return self.template_directory
        package_dir = os.path.abspath(os.path.dirname(__file__))
        return os.path.join(package_dir, "templates")

    @classmethod
    def get_instance(
        cls,
        *,
        directory: str | os.PathLike[str] | None = None,
        args: typing.Sequence[str] | str | None = None,
        options: typing.Any | None = None,
        app: typing.Any | None = None,
    ) -> "Config":
        directory = str(directory or settings.migration_directory)
        config = cls(os.path.join(directory, "alembic.ini"))
        config.set_main_option("script_location", directory)

        if config.cmd_opts is None:
            config.cmd_opts = argparse.Namespace()

        for option in options or []:
            setattr(config.cmd_opts, option, True)

        if not hasattr(config.cmd_opts, "x"):
            if args is not None:
                config.cmd_opts.x = []
                if isinstance(args, list | tuple):
                    for arg in args:
                        config.cmd_opts.x.append(arg)
                else:
                    config.cmd_opts.x.append(args)
            else:
                config.cmd_opts.x = None

        migrate_wrapper = _get_migrate_wrapper(app)
        if migrate_wrapper is not None:
            config = migrate_wrapper.call_configure_callbacks(config)
        return config


def _get_migrate_wrapper(app: typing.Any | None = None) -> "Migrate | None":
    if app is not None and hasattr(app, SAFFIER_DB):
        migrate_state = getattr(app, SAFFIER_DB).get("migrate")
        if migrate_state is not None and hasattr(migrate_state, "migrate"):
            return cast("Migrate", migrate_state.migrate)

    instance = get_active_instance()
    active_app = getattr(instance, "app", None) if instance is not None else None
    if active_app is not None and hasattr(active_app, SAFFIER_DB):
        migrate_state = getattr(active_app, SAFFIER_DB).get("migrate")
        if migrate_state is not None and hasattr(migrate_state, "migrate"):
            return cast("Migrate", migrate_state.migrate)

    return None


def _get_config(
    app: typing.Any | None = None,
    directory: str | os.PathLike[str] | None = None,
    *,
    arg: typing.Any | None = None,
    options: typing.Any | None = None,
) -> Config:
    migrate_wrapper = _get_migrate_wrapper(app)
    if migrate_wrapper is not None:
        return cast("Config", migrate_wrapper.get_config(directory, arg=arg, options=options))
    return Config.get_instance(directory=directory, args=arg, options=options, app=app)


class Migrate(BaseExtra):
    """
    Main migration object that should be used in any application
    that requires Saffier to control the migration process.

    This process will always create an entry in any ASGI application
    if there isn't any.
    """

    def __init__(
        self,
        app: typing.Any,
        registry: "Registry",
        model_apps: dict[str, str] | tuple[str] | list[str] | None = None,
        compare_type: bool = True,
        render_as_batch: bool = True,
        directory: str | os.PathLike[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        warnings.warn(
            "`Migrate(...)` is deprecated. Prefer `saffier.Instance(...)` and "
            "`saffier.monkay.set_instance(...)` for application discovery and migrations.",
            DeprecationWarning,
            stacklevel=2,
        )

        self.app = app
        self.configure_callbacks: list[Callable] = []
        self.registry = registry
        self.model_apps = model_apps or {}

        assert isinstance(self.model_apps, (dict, tuple, list)), (
            "`model_apps` must be a dict of 'app_name:location' format or a list/tuple of strings."
        )

        if isinstance(self.model_apps, dict):
            self.model_apps = cast(dict[str, str], self.model_apps.values())

        models = self.check_db_models(self.model_apps)

        for name, _ in models.items():
            if name in self.registry.models:
                warnings.warn(
                    f"There is already a model with the name {name} declared. Overriding the model will occur unless you rename it.",
                    stacklevel=2,
                )

        if self.registry.models:
            self.registry.models = {**models, **self.registry.models}
        else:
            self.registry.models = models

        self.directory = str(directory or settings.migration_directory)
        self.alembic_ctx_kwargs = dict(settings.alembic_ctx_kwargs)
        self.alembic_ctx_kwargs.update(kwargs)
        self.alembic_ctx_kwargs["compare_type"] = compare_type
        self.alembic_ctx_kwargs["render_as_batch"] = render_as_batch

        self.set_saffier_extension(app)

    def check_db_models(
        self, model_apps: dict[str, str] | tuple[str] | list[str]
    ) -> dict[str, Any]:
        """Import and collect concrete models from configured application modules.

        Args:
            model_apps: Dotted module paths that should be scanned for models.

        Returns:
            dict[str, Any]: Mapping of model name to model class.
        """
        from saffier.core.db.models import Model, ReflectModel

        models: dict[str, Any] = {}

        for location in model_apps:
            module = import_module(location)
            members = inspect.getmembers(
                module,
                lambda attr: (
                    is_class_and_subclass(attr, Model)
                    and not attr.meta.abstract
                    and not is_class_and_subclass(attr, ReflectModel)
                ),
            )
            for name, model in members:
                models[name] = model
        return models

    def set_saffier_extension(self, app: Any) -> None:
        """Attach migration state to the application object.

        The method stores the migration wrapper in the conventional Saffier app
        extension slot and updates the active global instance so later CLI and
        runtime helpers can reuse the discovered application context.

        Args:
            app: Application object receiving the migration state.
        """
        migrate = MigrateConfig(self, self.registry, **self.alembic_ctx_kwargs)
        object_setattr(app, SAFFIER_DB, {})
        app._saffier_db["migrate"] = migrate
        _monkay.set_instance(
            Instance(
                registry=self.registry,
                app=app,
                path=getattr(app, "__saffier_path__", None),
            )
        )

    def configure(self, f: Callable) -> Any:
        self.configure_callbacks.append(f)
        return f

    def call_configure_callbacks(self, config: Config) -> Config:
        for f in self.configure_callbacks:
            config = f(config)
        return config

    def get_config(
        self,
        directory: str | None = None,
        arg: typing.Any | None = None,
        options: typing.Any | None = None,
    ) -> Any:
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
                config.cmd_opts.x = []
                if isinstance(arg, list | tuple):
                    for x in arg:
                        config.cmd_opts.x.append(x)
                else:
                    config.cmd_opts.x.append(arg)
            else:
                config.cmd_opts.x = None
        return self.call_configure_callbacks(config)


@catch_errors
def list_templates() -> None:
    """List all available migration repository templates."""
    config = Config()
    config.print_stdout("Available templates:\n")

    for name in sorted(os.listdir(config.get_template_directory())):
        with open(os.path.join(config.get_template_directory(), name, "README")) as readme:
            synopsis = next(readme).strip()
        config.print_stdout(f"{name} - {synopsis}")


@catch_errors
def init(
    app: typing.Any | None,
    directory: str | None = None,
    template: str | None = None,
    package: bool = False,
) -> None:
    """Initialize a new Alembic migration repository for Saffier."""
    if directory is None:
        directory = str(settings.migration_directory)

    template_directory = None

    if template is not None and ("/" in template or "\\" in template):
        template_directory, template = os.path.split(template)

    config = Config(template_directory=template_directory)
    config.set_main_option("script_location", directory)
    config.config_file_name = os.path.join(directory, "alembic.ini")
    migrate_wrapper = _get_migrate_wrapper(app)
    if migrate_wrapper is not None:
        config = migrate_wrapper.call_configure_callbacks(config)

    if template is None:
        template = DEFAULT_TEMPLATE_NAME
    command.init(config, directory, template, package)


@catch_errors
def revision(
    app: typing.Any | None,
    directory: str | None = None,
    message: str | None = None,
    autogenerate: bool = False,
    sql: bool = False,
    head: str = "head",
    splice: bool = False,
    branch_label: str | None = None,
    version_path: str | None = None,
    revision_id: typing.Any | None = None,
) -> None:
    """Create a new migration revision file.

    When `autogenerate` is enabled, Alembic compares the current database state
    with the registered Saffier models to populate the revision script.
    """
    options = ["autogenerate"] if autogenerate else None
    config = _get_config(app, directory, options=options)

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
    app: typing.Any | None,
    directory: str | None = None,
    message: str | None = None,
    sql: bool = False,
    head: str = "head",
    splice: bool = False,
    branch_label: str | None = None,
    version_path: str | None = None,
    revision_id: typing.Any | None = None,
    arg: typing.Any | None = None,
) -> None:
    """Create an autogenerated migration revision.

    This is the higher-level alias behind the `makemigrations` command.
    """
    config = _get_config(app, directory, options=["autogenerate"], arg=arg)

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
def edit(app: typing.Any | None, directory: str | None = None, revision: str = "current") -> None:
    """Open a revision file in Alembic's configured editor."""
    if alembic_version >= (1, 9, 4):
        config = _get_config(app, directory)
        command.edit(config, revision)
    else:
        raise RuntimeError("Alembic 1.9.4 or greater is required")


@catch_errors
def merge(
    app: typing.Any | None,
    directory: str | None = None,
    revisions: str | list[str] | tuple[str, ...] = "",
    message: str | None = None,
    branch_label: str | None = None,
    revision_id: str | None = None,
) -> None:
    """Merge multiple revision heads into a new migration file."""
    config = _get_config(app, directory)
    command.merge(
        config, revisions, message=message, branch_label=branch_label, rev_id=revision_id
    )


@catch_errors
def upgrade(
    app: typing.Any | None,
    directory: str | None = None,
    revision: str = "head",
    sql: bool = False,
    tag: str | None = None,
    arg: typing.Any | None = None,
) -> None:
    """Upgrade the database to a later revision."""
    config = _get_config(app, directory, arg=arg)
    command.upgrade(config, revision, sql=sql, tag=tag)


@catch_errors
def downgrade(
    app: typing.Any | None,
    directory: str | None = None,
    revision: str = "-1",
    sql: bool = False,
    tag: str | None = None,
    arg: typing.Any | None = None,
) -> None:
    """Downgrade the database to an earlier revision."""
    config = _get_config(app, directory, arg=arg)
    if sql and revision == "-1":
        revision = "head:-1"
    command.downgrade(config, revision, sql=sql, tag=tag)


@catch_errors
def show(
    app: typing.Any | None,
    directory: str | None = None,
    revision: str = "head",
) -> None:
    """Show the revision denoted by the given symbol."""
    config = _get_config(app, directory)
    command.show(config, revision)


@catch_errors
def history(
    app: typing.Any | None,
    directory: str | None = None,
    rev_range: typing.Any | None = None,
    verbose: bool = False,
    indicate_current: bool = False,
) -> None:
    """List changeset scripts in chronological order."""
    config = _get_config(app, directory)
    command.history(config, rev_range, verbose=verbose, indicate_current=indicate_current)


@catch_errors
def heads(
    app: typing.Any | None,
    directory: str | None = None,
    verbose: bool = False,
    resolve_dependencies: bool = False,
) -> None:
    """Show available revision heads in the migration repository."""
    config = _get_config(app, directory)
    command.heads(config, verbose=verbose, resolve_dependencies=resolve_dependencies)


@catch_errors
def branches(app: typing.Any | None, directory: str | None = None, verbose: bool = False) -> None:
    """Show branch points in the migration history."""
    config = _get_config(app, directory)
    command.branches(config, verbose=verbose)


@catch_errors
def current(app: typing.Any | None, directory: str | None = None, verbose: bool = False) -> None:
    """Display the current database revision."""
    config = _get_config(app, directory)
    command.current(config, verbose=verbose)


@catch_errors
def stamp(
    app: typing.Any | None,
    directory: str | None = None,
    revision: str = "head",
    sql: bool = False,
    tag: typing.Any | None = None,
) -> None:
    """'stamp' the revision table with the given revision; don't run any
    migrations"""
    config = _get_config(app, directory)
    command.stamp(config, revision, sql=sql, tag=tag)


@catch_errors
def check(
    app: typing.Any | None,
    directory: str | None = None,
) -> None:
    """Check whether model changes would generate new migration operations."""
    config = _get_config(app, directory)
    command.check(config)
