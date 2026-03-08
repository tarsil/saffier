from __future__ import annotations

from typing import TYPE_CHECKING, Any

from saffier.core.db.models.metaclasses import _set_related_name_for_foreign_keys
from saffier.core.db.relationships.related import RelatedField

if TYPE_CHECKING:
    from saffier.core.db.models.types import BaseModelType


def _check_replace_related_field(
    replace_related_field: bool
    | type[BaseModelType]
    | tuple[type[BaseModelType], ...]
    | list[type[BaseModelType]],
    model: type[BaseModelType],
) -> bool:
    if isinstance(replace_related_field, bool):
        return replace_related_field
    if not isinstance(replace_related_field, tuple | list):
        replace_related_field = (replace_related_field,)
    return any(refmodel is model for refmodel in replace_related_field)


class DatabaseMixin:
    @classmethod
    def real_add_to_registry(cls, **kwargs: Any):
        return super().real_add_to_registry(**kwargs)

    @classmethod
    def add_to_registry(cls, registry: Any, **kwargs: Any):
        return super().add_to_registry(registry, **kwargs)


__all__ = [
    "DatabaseMixin",
    "RelatedField",
    "_check_replace_related_field",
    "_set_related_name_for_foreign_keys",
]
