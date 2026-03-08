from __future__ import annotations

from typing import TYPE_CHECKING, Any, runtime_checkable

try:
    from typing import Protocol
except ImportError:  # pragma: nocover
    from typing_extensions import Protocol  # type: ignore


if TYPE_CHECKING:  # pragma: nocover
    from saffier import Model


@runtime_checkable
class ManyRelationProtocol(Protocol):
    """Structural contract for many-to-many relation manager implementations.

    Many relation helpers inside Saffier only depend on a small async API for
    staging, creating, attaching, and removing related records. Using a
    protocol keeps those helpers independent from one concrete manager class
    while still documenting the behavior expected by the ORM.
    """

    instance: Model

    async def save_related(self) -> None: ...

    async def create(self, *args: Any, **kwargs: Any) -> Model | None: ...

    async def add(self, child: Model) -> Model | None: ...

    def stage(self, *children: Model) -> None: ...

    async def remove(self, child: Model | None = None) -> None: ...

    async def add_many(self, *children: Model) -> list[Model | None]: ...

    async def remove_many(self, *children: Model) -> None: ...
