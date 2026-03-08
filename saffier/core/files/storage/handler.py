from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any

from saffier.conf import settings
from saffier.conf.module_import import import_string
from saffier.exceptions import InvalidStorageError

if TYPE_CHECKING:
    from saffier.core.files.storage.base import Storage


class StorageHandler:
    def __init__(self, backends: dict[str, Any] | None = None) -> None:
        self._backends = deepcopy(backends) if backends is not None else None
        self._storages: dict[str, Storage] = {}

    @property
    def backends(self) -> dict[str, Any]:
        if self._backends is None:
            self._backends = deepcopy(settings.storages)
        return self._backends

    def __copy__(self) -> StorageHandler:
        return StorageHandler(self._backends)

    def clear(self) -> None:
        self._storages.clear()

    def reload(self) -> None:
        self._backends = None
        self._storages.clear()

    def __getitem__(self, alias: str) -> Storage:
        storage = self._storages.get(alias)
        if storage is not None:
            return storage

        params = self.backends.get(alias)
        if params is None:
            raise InvalidStorageError(f"Could not find config for '{alias}' in settings.storages.")

        storage = self.create_storage(params)
        storage.name = alias
        self._storages[alias] = storage
        return storage

    def create_storage(self, params: dict[str, Any]) -> Storage:
        backend = params.get("backend")
        options = params.get("options", {})

        if not isinstance(options, dict):
            raise InvalidStorageError("Storage backend options must be a dictionary.")

        try:
            if isinstance(backend, str):
                storage_cls: type[Storage] = import_string(backend)
            elif isinstance(backend, type):
                storage_cls = backend
            elif hasattr(backend, "_open") and hasattr(backend, "_save"):
                return backend
            else:
                raise InvalidStorageError(
                    f"Invalid storage backend {backend!r}. Expected dotted path or storage class."
                )
        except ImportError as exc:
            raise InvalidStorageError(f"Could not find backend {backend!r}: {exc}") from exc

        return storage_cls(**options)


storages = StorageHandler()
