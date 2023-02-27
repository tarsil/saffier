import os
import sys
import typing
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from rich.console import Console

from saffier.migrations.constants import SAFFIER_DISCOVER_APP

console = Console()


@dataclass
class App:
    """Information about a loaded application."""

    path: str
    app: typing.Any


@dataclass
class MigrationEnv:
    path: typing.Optional[str] = None
    app: typing.Optional[typing.Any] = None

    def load_from_env(self, path: typing.Optional[str]) -> "MigrationEnv":
        """
        Loads the environment variables into the object.
        """
        cwd = Path().cwd()
        cwd_path = str(cwd)
        if cwd_path not in sys.path:
            sys.path.append(cwd_path)

        try:
            import dotenv

            dotenv.load_dotenv()
        except ImportError:
            ...

        _path = os.getenv(SAFFIER_DISCOVER_APP) if not path else path
        _app = self.find_app(path=_path)

        return MigrationEnv(path=_app.path, app=_app.app)

    def import_app_from_string(cls, path: str):
        module_str_path, app_name = path.split(":")
        module = import_module(module_str_path)
        app = getattr(module, app_name)
        return App(path=path, app=app)

    def find_app(self, path: str) -> App:
        """
        Loads the application based on the path provided via env var.
        """
        console.print(f"Loading the application: [bright_green]{path} from env.")
        return self.import_app_from_string(path)
