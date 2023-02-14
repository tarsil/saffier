import argparse
import os
import sys
import typing
from functools import wraps

import toml
from alembic import __version__ as __alembic_version__
from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.util import CommandError
from loguru import logger

from saffier.db.connection import Database
from saffier.exceptions import ImproperlyConfigured
from saffier.management.migrator.decorators import catch_errors
from saffier.types import DictAny

alembic_version = tuple([int(v) for v in __alembic_version__.split(".")[0:3]])


class MigrateConfig:
    def __init__(self, migrate: typing.Any, database: typing.Any, **kwargs: DictAny) -> None:
        self.migrate = migrate
        self.database = database
        self.directory = migrate.directory
        self.config_args = kwargs

    @property
    def metadata(self):
        return self.database.metadata


class Config(AlembicConfig):
    def __init__(self, *args, **kwargs):
        self.template_directory = kwargs.pop("template_directory", None)
        super().__init__(*args, **kwargs)

    def get_template_directory(self) -> str:
        if self.template_directory:
            return self.template_directory
        package = os.path.abspath(os.path.dirname(__file__))
        return os.path.join(package, "templates")


class Migrate:
    """
    Main object that allows migrations inside the application.
    """

    def __init__(
        self,
        database: typing.Any,
        directory: typing.Optional[str] = None,
        config_filename: typing.Optional[str] = None,
        command="db",
        compare_type: bool = True,
        render_as_batch: bool = True,
        **kwargs: DictAny,
    ) -> None:
        self.configure_callbacks = []
        self.database = database
        self.directory = directory or "templates"
        self.config_filename = config_filename or "pyproject.toml"
        self.command = command
        self.alembic_ctx_kwargs = kwargs
        self.alembic_ctx_kwargs["compare_types"] = compare_type
        self.alembic_ctx_kwargs["render_as_batch"] = render_as_batch

    def setup(self, fn: typing.Any) -> typing.Any:
        self.configure_callbacks.append(fn)
        return fn

    def call_configure_callbacks(self, config: typing.Any) -> typing.Any:
        for fn in self.configure_callbacks:
            config = fn(config)
        return config

    def get_config(
        self,
        directory: typing.Optional[str] = None,
        arg: typing.Any = None,
        options: typing.Any = None,
    ) -> typing.Any:
        if directory is None:
            directory = self.directory

        directory = str(directory)
        config = Config(os.path.join(directory, self.config_filename))
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


def load_toml_config(filename: str):
    """
    Loads the TOML configuration for saffier.
    """
    try:
        return toml.load(filename)["tool"]["saffier"]
    except FileNotFoundError as e:
        raise ImproperlyConfigured(detail=str(e))


@catch_errors
def list_templates():
    config = Config()
    config.print_stdout("Available templates: \n")
    for template_name in sorted(os.listdir(config.get_template_directory())):
        with open(
            os.path.join(config.get_template_directory(), template_name, "README")
        ) as readme:
            synopsis = next(readme).strip()
        config.print_stdout(f"{template_name} - {synopsis}")


@catch_errors
def initialize(
    directory: str = None,
    multi_database: bool = False,
    template: typing.Any = None,
    package: bool = False,
    filename: str = "",
):
    """
    Creates the migration folder
    """

    if directory is None:
        ...
