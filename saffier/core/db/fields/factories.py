from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from .base import Field

FieldType = TypeVar("FieldType", bound=Field)


def make_field(field_cls: type[FieldType], /, **defaults: Any) -> Callable[..., FieldType]:
    """
    Build lightweight field constructor callables with shared defaults.

    This keeps Saffier field declarations Python-native while offering an
    ergonomic extension point for repetitive field definitions.
    """

    def factory(**overrides: Any) -> FieldType:
        return field_cls(**{**defaults, **overrides})

    return factory


__all__ = ["make_field"]
