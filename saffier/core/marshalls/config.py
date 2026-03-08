from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from saffier.core.db.models.model import Model


class ConfigMarshall(TypedDict, total=False):
    model: type[Model] | str
    fields: list[str] | None
    exclude: list[str] | None
    primary_key_read_only: bool
    exclude_autoincrement: bool
    exclude_read_only: bool


__all__ = ["ConfigMarshall"]
