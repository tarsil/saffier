from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from saffier.conf import _monkay
from saffier.core.files.storage.handler import StorageHandler

if TYPE_CHECKING:
    from saffier.core.connection.registry import Registry

_MIGRATE_ATTR = "_saffier_db"
_EXTRA_ATTR = "_saffier_extra"


@dataclass
class Instance:
    registry: Registry
    app: Any | None = None
    path: str | None = None
    storages: StorageHandler = field(default_factory=StorageHandler)


def build_instance_from_app(
    app: Any,
    *,
    path: str | None = None,
    storages: StorageHandler | None = None,
) -> Instance | None:
    registry = None

    migrate_state = getattr(app, _MIGRATE_ATTR, None)
    if isinstance(migrate_state, dict):
        migrate_config = migrate_state.get("migrate")
        registry = getattr(migrate_config, "registry", None)

    if registry is None:
        extra_state = getattr(app, _EXTRA_ATTR, None)
        if isinstance(extra_state, dict):
            extra_config = extra_state.get("extra")
            registry = getattr(extra_config, "registry", None)

    if registry is None:
        return None

    current_instance = _monkay.instance
    if storages is None and current_instance is not None:
        storages = getattr(current_instance, "storages", None)

    return Instance(
        registry=registry,
        app=app,
        path=path,
        storages=StorageHandler() if storages is None else storages,
    )


def set_instance_from_app(app: Any, *, path: str | None = None) -> Instance | None:
    instance = build_instance_from_app(app, path=path)
    if instance is None:
        return None
    _monkay.set_instance(instance)
    return instance


def get_active_instance() -> Instance | Any | None:
    return _monkay.instance
