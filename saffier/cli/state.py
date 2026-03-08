from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from saffier._instance import set_instance_from_app
from saffier.cli.env import MigrationEnv
from saffier.conf import _monkay
from saffier.exceptions import CommandEnvironmentError

_migration_env: ContextVar[MigrationEnv | None] = ContextVar("saffier_migration_env", default=None)


def set_migration_env(env: MigrationEnv) -> None:
    _migration_env.set(env)


def clear_migration_env() -> None:
    _migration_env.set(None)


def get_migration_env() -> MigrationEnv:
    instance = _monkay.instance
    if instance is not None:
        return MigrationEnv(
            path=getattr(instance, "path", None),
            app=getattr(instance, "app", None),
        )
    env = _migration_env.get()
    if env is None:
        raise CommandEnvironmentError(
            detail=(
                "Could not find Saffier in any application. "
                "Set env `SAFFIER_DEFAULT_APP` or use `--app` instead."
            )
        )
    return env


def get_migration_instance() -> Any:
    instance = _monkay.instance
    if instance is not None:
        return instance

    env = _migration_env.get()
    if env is not None and env.app is not None:
        instance = set_instance_from_app(env.app, path=env.path)
        if instance is not None:
            return instance

    raise CommandEnvironmentError(
        detail=(
            "Could not resolve the active Saffier instance. "
            "Set env `SAFFIER_DEFAULT_APP` or use `--app` instead."
        )
    )


def get_migration_app() -> Any | None:
    instance = _monkay.instance
    if instance is not None:
        return getattr(instance, "app", None)

    env = _migration_env.get()
    if env is None:
        raise CommandEnvironmentError(
            detail=(
                "Could not find Saffier in any application. "
                "Set env `SAFFIER_DEFAULT_APP` or use `--app` instead."
            )
        )
    if env.app is None:
        raise CommandEnvironmentError(
            detail=(
                "Could not load Saffier application. "
                "Set env `SAFFIER_DEFAULT_APP` or use `--app` instead."
            )
        )
    return env.app


def get_migration_registry() -> Any:
    instance = get_migration_instance()
    registry = getattr(instance, "registry", None)
    if registry is None:
        raise CommandEnvironmentError(detail="Could not resolve the active Saffier registry.")
    return registry
