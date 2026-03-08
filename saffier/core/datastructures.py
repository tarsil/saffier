from __future__ import annotations

from typing import Any


class HashableBaseModel:
    """
    Lightweight mutable object used by Saffier internals.
    """

    __slots__ = ("__dict__", "__weakref__")

    def __init__(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __hash__(self) -> int:
        values: dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if isinstance(value, (list, set)):
                values[key] = tuple(value)
            else:
                values[key] = value
        return hash((type(self),) + tuple(values))


class ArbitraryHashableBaseModel(HashableBaseModel):
    """
    Backwards-compatible alias for internals that allow dynamic attributes.
    """
