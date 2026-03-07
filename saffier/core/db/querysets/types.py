from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias, TypeVar

from saffier.protocols.queryset import QuerySetProtocol

if TYPE_CHECKING:
    import sqlalchemy

    from saffier.core.db.models.types import BaseModelType

SaffierModel = TypeVar("SaffierModel", bound="BaseModelType")
SaffierEmbedTarget = TypeVar("SaffierEmbedTarget")

tables_and_models_type: TypeAlias = dict[str, tuple["sqlalchemy.Table", type["BaseModelType"]]]
reference_select_type: TypeAlias = dict[str, Any]
QuerySetType: TypeAlias = QuerySetProtocol

__all__ = [
    "QuerySetType",
    "SaffierEmbedTarget",
    "SaffierModel",
    "reference_select_type",
    "tables_and_models_type",
]
