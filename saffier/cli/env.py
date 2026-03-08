import os
import sys
import typing
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from types import ModuleType

from saffier._instance import set_instance_from_app
from saffier.cli.constants import (
    DISCOVERY_FILES,
    DISCOVERY_FUNCTIONS,
    SAFFIER_DB,
    SAFFIER_DISCOVER_APP,
    SAFFIER_EXTRA,
)
from saffier.conf import _monkay
from saffier.exceptions import CommandEnvironmentError


@dataclass
class Scaffold:
    """
    Simple Application scaffold that holds the
    information about the app and the path to
    the same app.
    """

    path: str
    app: typing.Any


@dataclass
class MigrationEnv:
    """
    Loads an arbitraty application into the object
    and returns the App.
    """

    path: str | None = None
    app: typing.Any | None = None
    command_path: str | None = None

    def load_from_env(
        self, path: str | None = None, enable_logging: bool = True
    ) -> "MigrationEnv":
        """
        Loads the environment variables into the scaffold.
        """
        # Adds the current path where the command is being invoked
        # To the system path
        cwd = Path().cwd()
        command_path = str(cwd)
        if command_path not in sys.path:
            sys.path.append(command_path)
        try:
            import dotenv

            dotenv.load_dotenv()
        except ImportError:
            ...

        _path = path if path else os.getenv(SAFFIER_DISCOVER_APP)
        _app = self.find_app(path=_path, cwd=cwd)

        return MigrationEnv(path=_app.path, app=_app.app)

    def import_app_from_string(cls, path: str | None = None) -> Scaffold:
        if path is None:
            raise CommandEnvironmentError(
                detail="Path cannot be None. Set env `SAFFIER_DEFAULT_APP` or use `--app` instead."
            )
        if ":" not in path:
            module = import_module(path)
            if _monkay.instance is not None:
                app = getattr(_monkay.instance, "app", None)
                return Scaffold(path=path, app=app)
            scaffold = cls._find_app_in_module(module, path)
            if scaffold is not None:
                set_instance_from_app(scaffold.app, path=scaffold.path)
                return scaffold
            raise CommandEnvironmentError(
                detail=(
                    f'Imported module "{path}" but did not find an active Saffier instance or '
                    "a compatible app object."
                )
            )
        module_str_path, app_name = path.split(":")
        module = import_module(module_str_path)
        app = getattr(module, app_name)
        if callable(app) and not hasattr(app, SAFFIER_DB) and not hasattr(app, SAFFIER_EXTRA):
            app = app()
        set_instance_from_app(app, path=path)
        return Scaffold(path=path, app=app)

    def _scaffold_from_candidate(self, value: typing.Any, path: str) -> Scaffold | None:
        if hasattr(value, SAFFIER_DB) or hasattr(value, SAFFIER_EXTRA):
            return Scaffold(app=value, path=path)
        return None

    def _find_app_in_module(self, module: ModuleType, dotted_path: str) -> Scaffold | None:
        for attr, value in module.__dict__.items():
            scaffold = self._scaffold_from_candidate(value, f"{dotted_path}:{attr}")
            if scaffold is not None:
                return scaffold

        for func in DISCOVERY_FUNCTIONS:
            if hasattr(module, func):
                app_path = f"{dotted_path}:{func}"
                fn = getattr(module, func)()
                scaffold = self._scaffold_from_candidate(fn, app_path)
                if scaffold is not None:
                    return scaffold
        return None

    def _get_folders(self, path: Path) -> list[str]:
        """
        Lists all the folders and checks if there is any file from the DISCOVERY_FILES available
        """
        return [directory.path for directory in os.scandir(path) if directory.is_dir()]

    def _find_app_in_folder(self, path: Path, cwd: Path) -> Scaffold | None:
        """
        Iterates inside the folder and looks up to the DISCOVERY_FILES.
        """
        for discovery_file in DISCOVERY_FILES:
            filename = f"{str(path)}/{discovery_file}"
            if not os.path.exists(filename):
                continue

            file_path = path / discovery_file
            dotted_path = ".".join(file_path.relative_to(cwd).with_suffix("").parts)
            module = import_module(dotted_path)
            scaffold = self._find_app_in_module(module, dotted_path)
            if scaffold is not None:
                return scaffold
        return None

    def _find_loaded_app_path(self, app: typing.Any) -> str | None:
        for module in tuple(sys.modules.values()):
            if not isinstance(module, ModuleType):
                continue
            for attr, value in getattr(module, "__dict__", {}).items():
                if value is app:
                    return f"{module.__name__}:{attr}"
        return None

    def load_from_instance(self, instance: typing.Any) -> "MigrationEnv":
        app = getattr(instance, "app", instance)
        path = getattr(instance, "path", None) or self._find_loaded_app_path(app)

        if path is None and app is not None:
            path = f"{app.__module__}:app"

        if path is None:
            raise CommandEnvironmentError(
                detail="Could not resolve the Saffier app from the active instance."
            )

        return MigrationEnv(path=path, app=app)

    def find_app(self, path: str | None, cwd: Path) -> Scaffold:
        """
        Loads the application based on the path provided via env var.

        If no --app is provided, goes into auto discovery up to one level.
        """

        if path:
            return self.import_app_from_string(path)

        scaffold: Scaffold | None = None

        # Check current folder
        scaffold = self._find_app_in_folder(cwd, cwd)  # type: ignore
        if scaffold:
            return scaffold

        # Goes into auto discovery mode for one level, only.
        folders = self._get_folders(cwd)

        for folder in folders:
            folder_path = cwd / folder
            scaffold = self._find_app_in_folder(folder_path, cwd)  # type: ignore

            if not scaffold:
                continue
            break

        if not scaffold:
            raise CommandEnvironmentError(detail="Could not find Saffier in any application.")
        return scaffold
