from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .base import Field


class SupportsColumns(Protocol):
    is_virtual: bool

    def has_column(self) -> bool: ...

    def get_column(self, name: str) -> Any: ...


class SupportsEmbeddedFields(Protocol):
    def get_embedded_fields(
        self,
        field_name: str,
        existing_fields: Mapping[str, Field],
    ) -> dict[str, Field]: ...


FieldMapping = dict[str, "Field"]

__all__ = ["FieldMapping", "SupportsColumns", "SupportsEmbeddedFields"]
