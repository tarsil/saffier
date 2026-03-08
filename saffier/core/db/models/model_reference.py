from __future__ import annotations

import inspect
from typing import Any, ClassVar

from saffier.core.datastructures import HashableBaseModel
from saffier.exceptions import ModelReferenceError


class ModelRef(HashableBaseModel):
    """Pure Python reference object used by `RefForeignKey`.

    `ModelRef` instances let callers stage nested related inserts without
    importing or instantiating the full target ORM model up front.
    """

    __related_name__: ClassVar[str]
    __model_ref_fields__: ClassVar[tuple[str, ...]] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls is ModelRef:
            return

        related_name = getattr(cls, "__related_name__", None)
        if not related_name:
            raise ModelReferenceError(
                "'__related_name__' must be declared when subclassing ModelRef."
            )

        field_names: list[str] = []
        for base in reversed(cls.__mro__):
            annotations = inspect.get_annotations(base, eval_str=False)
            for field_name in annotations:
                if field_name.startswith("_") or field_name == "__related_name__":
                    continue
                if field_name not in field_names:
                    field_names.append(field_name)

        cls.__model_ref_fields__ = tuple(field_names)

    def __init__(self, **kwargs: Any) -> None:
        unexpected = sorted(key for key in kwargs if key not in self.__model_ref_fields__)
        if unexpected:
            joined = ", ".join(unexpected)
            raise TypeError(f"Unexpected ModelRef field(s): {joined}.")

        missing: list[str] = []
        for field_name in self.__model_ref_fields__:
            if field_name in kwargs:
                value = kwargs[field_name]
            elif hasattr(type(self), field_name):
                value = getattr(type(self), field_name)
            else:
                missing.append(field_name)
                continue
            setattr(self, field_name, value)

        if missing:
            joined = ", ".join(missing)
            raise TypeError(f"Missing required ModelRef field(s): {joined}.")

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return cls.__model_ref_fields__

    def model_dump(
        self,
        *,
        include: set[str] | None = None,
        exclude: set[str] | None = None,
        exclude_none: bool = False,
    ) -> dict[str, Any]:
        values = {
            field_name: getattr(self, field_name)
            for field_name in self.__model_ref_fields__
            if hasattr(self, field_name)
        }

        if include is not None:
            values = {key: value for key, value in values.items() if key in include}
        if exclude is not None:
            values = {key: value for key, value in values.items() if key not in exclude}
        if exclude_none:
            values = {key: value for key, value in values.items() if value is not None}
        return values

    def __eq__(self, other: Any) -> bool:
        if self.__class__ is not other.__class__:
            return False
        return self.model_dump() == other.model_dump()

    def __repr__(self) -> str:
        values = ", ".join(f"{key}={value!r}" for key, value in self.model_dump().items())
        return f"{self.__class__.__name__}({values})"
