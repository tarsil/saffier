from __future__ import annotations

import builtins
import copy
import inspect
import json
import os
import sys
from collections.abc import Callable, Sequence
from functools import cached_property
from pathlib import Path
from types import UnionType
from typing import (
    Annotated,
    Any,
    ClassVar,
    TypeAlias,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from monkay.types import ExtensionProtocol as SettingsExtensionProtocol

SettingsExtensionDefinition: TypeAlias = (
    SettingsExtensionProtocol[Any, Any]
    | type[SettingsExtensionProtocol[Any, Any]]
    | Callable[[], SettingsExtensionProtocol[Any, Any]]
)


def _is_classvar_annotation(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is ClassVar:
        return True
    if isinstance(annotation, str):
        return annotation.startswith("ClassVar[") or annotation.startswith("typing.ClassVar[")
    return False


def safe_get_type_hints(cls: type) -> dict[str, Any]:
    """Collect type hints across the full MRO.

    The helper falls back gracefully when some annotations cannot be fully
    resolved, which is important for settings classes that may reference optional
    imports or forward declarations.
    """
    type_hints: dict[str, Any] = {}

    for base in reversed(cls.__mro__):
        if base is object:
            continue

        try:
            base_hints = get_type_hints(base, include_extras=True)
        except Exception:
            base_hints = getattr(base, "__annotations__", {})

        for name, annotation in base_hints.items():
            if name.startswith("_") or _is_classvar_annotation(annotation):
                continue
            type_hints[name] = annotation

    return type_hints


class BaseSettings:
    """Python-native settings base with environment casting and inheritance.

    Settings values are resolved from explicit constructor kwargs first, then
    from uppercased environment variables, and finally from class-level default
    values.
    """

    __type_hints__: builtins.dict[str, Any]
    __truthy__: set[str] = {"1", "true", "yes", "on", "y"}

    def __init_subclass__(cls) -> None:
        if cls.__dict__.get("__type_hints__") is None:
            cls.__type_hints__ = safe_get_type_hints(cls)

    def __init__(self, **kwargs: Any) -> None:
        extras = {key: value for key, value in kwargs.items() if key not in self.__type_hints__}

        for key, annotation in self.__type_hints__.items():
            if key in kwargs:
                value = kwargs[key]
            else:
                env_value = os.getenv(key.upper())
                if env_value is not None:
                    value = self._cast(env_value, annotation)
                else:
                    value = self._clone_default_value(key)
            setattr(self, key, value)

        for key, value in extras.items():
            setattr(self, key, value)

        self.post_init()

    def post_init(self) -> None:
        """Hook for subclasses that need to finalize settings after initialization."""

    def _clone_default_value(self, key: str) -> Any:
        if hasattr(type(self), key):
            return copy.deepcopy(getattr(type(self), key))
        return None

    def _resolve_string_type(self, type_name: str) -> Any:
        base_name = type_name.split("[", 1)[0]

        module = sys.modules.get(self.__class__.__module__)
        if module is not None and hasattr(module, base_name):
            return getattr(module, base_name)
        if hasattr(builtins, base_name):
            return getattr(builtins, base_name)
        return None

    def _normalize_annotation(self, annotation: Any) -> Any:
        origin = get_origin(annotation)
        if origin is Annotated:
            return self._normalize_annotation(get_args(annotation)[0])
        if isinstance(annotation, str):
            resolved = self._resolve_string_type(annotation)
            if resolved is not None:
                return resolved
        return annotation

    def _cast_sequence(self, value: str, origin: Any) -> Any:
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            loaded = [item.strip() for item in value.split(",") if item.strip()]

        if not isinstance(loaded, list | tuple | set):
            raise ValueError(f"Cannot cast value '{value}' to sequence type")

        if origin is tuple:
            return tuple(loaded)
        if origin is set:
            return set(loaded)
        return list(loaded)

    def _cast_dict(self, value: str) -> builtins.dict[str, Any]:
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Cannot cast value '{value}' to type 'dict'") from exc

        if not isinstance(loaded, dict):
            raise ValueError(f"Cannot cast value '{value}' to type 'dict'")
        return loaded

    def _cast(self, value: str, annotation: Any) -> Any:
        annotation = self._normalize_annotation(annotation)
        origin = get_origin(annotation)

        if origin is Union or origin is UnionType:
            errors: list[ValueError] = []
            for arg in get_args(annotation):
                if arg is type(None):
                    continue
                try:
                    return self._cast(value, arg)
                except ValueError as exc:
                    errors.append(exc)
            if errors:
                raise errors[-1]
            return value

        if annotation in {Any, object}:
            return value

        if annotation is bool or str(annotation) == "bool":
            return value.lower() in self.__truthy__

        if origin in {list, tuple, set}:
            return self._cast_sequence(value, origin)

        if origin is dict or annotation is dict:
            return self._cast_dict(value)

        if annotation is int:
            return int(value, 0)

        if annotation is float:
            return float(value)

        if annotation is str:
            return value

        if annotation is Path or annotation is os.PathLike or origin is os.PathLike:
            return Path(value)

        if (
            inspect.isclass(annotation)
            and issubclass(annotation, Sequence)
            and annotation is not str
        ):
            return annotation(self._cast_sequence(value, list))

        if inspect.isclass(annotation):
            return annotation(value)

        type_name = getattr(annotation, "__name__", str(annotation))
        raise ValueError(f"Cannot cast value '{value}' to type '{type_name}'")

    def dict(
        self,
        exclude_none: bool = False,
        upper: bool = False,
        exclude: set[str] | None = None,
        include_properties: bool = False,
    ) -> builtins.dict[str, Any]:
        result: dict[str, Any] = {}
        exclude = exclude or set()

        for key in self.__type_hints__:
            if key in exclude:
                continue
            value = getattr(self, key, None)
            if exclude_none and value is None:
                continue
            result[key.upper() if upper else key] = value

        if include_properties:
            for name, _member in inspect.getmembers(
                type(self), lambda obj: isinstance(obj, property | cached_property)
            ):
                if name in exclude or name in self.__type_hints__:
                    continue
                try:
                    value = getattr(self, name)
                except Exception:
                    continue
                if exclude_none and value is None:
                    continue
                result[name.upper() if upper else name] = value

        return result

    def tuple(
        self,
        exclude_none: bool = False,
        upper: bool = False,
        exclude: set[str] | None = None,
        include_properties: bool = False,
    ) -> list[builtins.tuple[str, Any]]:
        return list(
            self.dict(
                exclude_none=exclude_none,
                upper=upper,
                exclude=exclude,
                include_properties=include_properties,
            ).items()
        )

    def model_copy(
        self, *, update: builtins.dict[str, Any] | None = None, deep: bool = False
    ) -> BaseSettings:
        payload = self.dict()
        if update:
            payload.update(update)
        if deep:
            payload = copy.deepcopy(payload)
        return self.__class__(**payload)


__all__ = [
    "BaseSettings",
    "SettingsExtensionDefinition",
    "SettingsExtensionProtocol",
    "safe_get_type_hints",
]
