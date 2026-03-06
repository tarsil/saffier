from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from saffier.cli.env import MigrationEnv
from saffier.exceptions import CommandEnvironmentError

_migration_env: ContextVar[MigrationEnv | None] = ContextVar("saffier_migration_env", default=None)


def set_migration_env(env: MigrationEnv) -> None:
    _migration_env.set(env)


def clear_migration_env() -> None:
    _migration_env.set(None)


def get_migration_env() -> MigrationEnv:
    env = _migration_env.get()
    if env is None:
        raise CommandEnvironmentError(
            detail=(
                "Could not find Saffier in any application. "
                "Set env `SAFFIER_DEFAULT_APP` or use `--app` instead."
            )
        )
    return env


def get_migration_app() -> Any:
    env = get_migration_env()
    if env.app is None:
        raise CommandEnvironmentError(
            detail=(
                "Could not load Saffier application. "
                "Set env `SAFFIER_DEFAULT_APP` or use `--app` instead."
            )
        )
    return env.app
