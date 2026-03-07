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
    """Defines the what needs to be implemented when using the ManyRelationProtocol"""

    instance: Model

    async def save_related(self) -> None: ...

    async def create(self, *args: Any, **kwargs: Any) -> Model | None: ...

    async def add(self, child: Model) -> Model | None: ...

    def stage(self, *children: Model) -> None: ...

    async def remove(self, child: Model | None = None) -> None: ...

    async def add_many(self, *children: Model) -> list[Model | None]: ...

    async def remove_many(self, *children: Model) -> None: ...
