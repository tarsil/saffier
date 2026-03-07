from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, TypeAlias, TypedDict, Union

if TYPE_CHECKING:
    from saffier.core.db.fields.base import BaseFieldType

    from .fields import FactoryField


class _ModelFactoryContext(TypedDict):
    faker: Any
    exclude_autoincrement: bool
    depth: int
    callcounts: dict[int, int]


if TYPE_CHECKING:

    class ModelFactoryContext(_ModelFactoryContext, Protocol):
        def __getattr__(self, name: str) -> Any: ...
else:
    ModelFactoryContext = _ModelFactoryContext


FactoryParameterCallback: TypeAlias = Callable[
    [
        "FactoryField",
        ModelFactoryContext,
        str,
    ],
    Any,
]

FactoryParameters: TypeAlias = dict[str, Any | FactoryParameterCallback]

FactoryCallback: TypeAlias = Callable[
    [
        "FactoryField",
        ModelFactoryContext,
        dict[str, Any],
    ],
    Any,
]

FieldFactoryCallback: TypeAlias = str | FactoryCallback

FactoryFieldType: TypeAlias = Union[str, "BaseFieldType", type["BaseFieldType"]]
