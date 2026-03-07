from __future__ import annotations

import inspect
import typing
from collections.abc import Awaitable
from functools import cached_property
from typing import Any, ClassVar, cast, get_args, get_origin

from saffier.core.marshalls.config import ConfigMarshall
from saffier.core.marshalls.fields import BaseMarshallField
from saffier.core.marshalls.metaclasses import MarshallFieldBinding, MarshallMeta
from saffier.core.utils.concurrency import run_concurrently
from saffier.core.utils.sync import run_sync
from saffier.exceptions import ValidationError

if typing.TYPE_CHECKING:
    from saffier.core.db.models.model import Model
    from saffier.core.marshalls.metaclasses import MarshallFieldBinding

_UNSET = object()
_EXCLUDED = object()
_MISSING = object()
_NO_DEFAULT = object()

excludes_marshall: set[str] = {"context", "instance", "_instance"}


def _coerce_union(value: Any, annotation: Any) -> Any:
    union_args = [arg for arg in get_args(annotation) if arg is not type(None)]
    for arg in union_args:
        try:
            return _coerce_value(value, arg)
        except (TypeError, ValueError, ValidationError):
            continue
    return value


def _coerce_value(value: Any, annotation: Any) -> Any:
    if value is None:
        return None

    origin = get_origin(annotation)
    if origin is typing.Union:
        return _coerce_union(value, annotation)
    if origin in (list, set, tuple):
        if not isinstance(value, origin):
            raise TypeError(f"Expected {origin.__name__}.")
        return value
    if origin is dict:
        if not isinstance(value, dict):
            raise TypeError("Expected dict.")
        return value
    if annotation in (Any, typing.Any, object):
        return value
    if annotation is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        raise TypeError("Expected bool.")
    if isinstance(annotation, type) and not isinstance(value, annotation):
        raise TypeError(f"Expected {annotation.__name__}.")
    return value


class BaseMarshall:
    marshall_config: ClassVar[ConfigMarshall]
    model_fields: ClassVar[dict[str, MarshallFieldBinding]]
    __show_pk__: ClassVar[bool] = False
    __lazy__: ClassVar[bool] = False
    __incomplete_fields__: ClassVar[tuple[str, ...]] = ()
    __custom_fields__: ClassVar[dict[str, BaseMarshallField]] = {}
    __local_fields__: ClassVar[dict[str, BaseMarshallField]] = {}

    def __init__(self, instance: None | Model = None, **kwargs: Any) -> None:
        context = kwargs.pop("context", {})
        lazy = kwargs.pop("__lazy__", type(self).__lazy__)
        object.__setattr__(self, "context", context or {})
        object.__setattr__(self, "_instance", None)
        object.__setattr__(self, "_setup_used", False)
        object.__setattr__(self, "_tracking_enabled", False)
        object.__setattr__(self, "_explicit_fields", set(kwargs.keys()))

        data: dict[str, Any] = {}
        if instance is not None:
            data.update(self._data_from_instance(instance))
        data.update(kwargs)

        for field_name, binding in type(self).model_fields.items():
            if field_name in data:
                value = self._validate_field(binding, data[field_name])
            elif binding.has_default:
                value = binding.get_default_value()
            elif binding.null:
                value = None
            elif (
                binding.required
                and instance is None
                and field_name in self._required_input_fields()
            ):
                raise ValidationError(
                    text=f"{field_name} is required.", code="required", key=field_name
                )
            else:
                value = None
            object.__setattr__(self, field_name, value)

        object.__setattr__(self, "_tracking_enabled", True)

        if instance is not None:
            self.instance = instance
        elif not lazy:
            built = self._setup()
            self._instance = built
            self._resolve_serializer(built)
            self._setup_used = True

    def __setattr__(self, key: str, value: Any) -> None:
        if getattr(self, "_tracking_enabled", False) and key in type(self).model_fields:
            self._explicit_fields.add(key)
            value = self._validate_field(type(self).model_fields[key], value)
        object.__setattr__(self, key, value)

    @classmethod
    def _required_input_fields(cls) -> set[str]:
        return {
            name
            for name, binding in cls.model_fields.items()
            if binding.required and name in cls.marshall_config["model"].fields  # type: ignore[index]
        }

    def _data_from_instance(self, instance: Model) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for field_name in type(self).model_fields:
            if field_name in excludes_marshall:
                continue
            if hasattr(instance, field_name):
                data[field_name] = getattr(instance, field_name)
        return data

    def _validate_field(self, binding: MarshallFieldBinding, value: Any) -> Any:
        if (
            binding.model_field is not None
            and binding.name in self.marshall_config["model"].fields
        ):  # type: ignore[index]
            return binding.model_field.validator.check(value)
        field = binding.marshall_field
        if field is None:
            return value
        if value is None:
            if field.null:
                return None
            if field.has_default():
                return field.get_default_value()
            return None
        return _coerce_value(field.validate(value), binding.field_type)

    def _setup(self) -> Model:
        klass = type(self)
        if klass.__incomplete_fields__:
            raise RuntimeError(
                f"'{klass.__name__}' is an incomplete Marshall. For creating new instances, it lacks following fields: [{', '.join(klass.__incomplete_fields__)}]."
            )

        model = cast("type[Model]", self.marshall_config["model"])
        data: dict[str, Any] = {}
        for field_name in model.fields:
            if field_name not in type(self).model_fields:
                continue
            field = model.fields[field_name]
            if field.primary_key and field.autoincrement:
                continue
            data[field_name] = getattr(self, field_name, None)

        return model(**data)

    @property
    def meta(self) -> Any:
        model = cast("type[Model]", self.marshall_config["model"])
        return model.meta

    @property
    def has_instance(self) -> bool:
        return self._instance is not None

    @property
    def instance(self) -> Model:
        if self._instance is None:
            built = self._setup()
            self._resolve_serializer(built)
            self._instance = built
            self._setup_used = True
        return self._instance

    @instance.setter
    def instance(self, value: Model) -> None:
        self._instance = value
        self._setup_used = False
        self._resolve_serializer(value)

    async def _resolve_async(self, name: str, awaitable: Awaitable[Any]) -> None:
        setattr(self, name, await awaitable)

    def _resolve_serializer(self, instance: Model) -> BaseMarshall:
        async_resolvers = []
        for name, field in type(self).__custom_fields__.items():
            if field.__is_method__:
                value = self._get_method_value(name, instance)
            else:
                attribute = getattr(instance, field.source or name)
                value = attribute() if callable(attribute) else attribute
            if inspect.isawaitable(value):
                async_resolvers.append(self._resolve_async(name, value))
                continue
            object.__setattr__(self, name, value)

        if async_resolvers:
            run_sync(run_concurrently(async_resolvers))
        return self

    def _get_method_value(self, name: str, instance: Model) -> Any:
        func = getattr(self, f"get_{name}")
        return func(instance)

    def _handle_primary_key(self, instance: Model) -> None:
        pk_name = instance.pkname
        if pk_name in type(self).model_fields:
            object.__setattr__(self, pk_name, getattr(instance, pk_name))

    @cached_property
    def valid_fields(self) -> dict[str, MarshallFieldBinding]:
        return {key: value for key, value in type(self).model_fields.items() if not value.exclude}

    @cached_property
    def fields(self) -> dict[str, BaseMarshallField]:
        return dict(type(self).__custom_fields__)

    def model_dump(
        self,
        include: set[str] | None = None,
        exclude: set[str] | None = None,
        exclude_none: bool = False,
        exclude_unset: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for field_name, binding in type(self).model_fields.items():
            if binding.exclude:
                continue
            if include is not None and field_name not in include:
                continue
            if exclude is not None and field_name in exclude:
                continue
            if (
                exclude_unset
                and field_name not in self._explicit_fields
                and field_name not in type(self).__custom_fields__
            ):
                continue

            value = getattr(self, field_name, None)
            if exclude_none and value is None:
                continue
            payload[field_name] = value
        return payload

    @classmethod
    def model_json_schema(
        cls,
        *,
        include_callable_defaults: bool = False,
        schema_generator: Any | None = None,
        mode: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del schema_generator, mode, kwargs
        properties: dict[str, Any] = {}
        required: list[str] = []
        for field_name, binding in cls.model_fields.items():
            if binding.exclude:
                continue
            schema = _annotation_to_schema(binding.field_type)
            if binding.has_default:
                default = binding.default
                if binding.callable_default:
                    default = default() if include_callable_defaults else _NO_DEFAULT
                if default is not _NO_DEFAULT:
                    schema["default"] = default
            if binding.null and "type" in schema:
                schema = {"anyOf": [schema, {"type": "null"}]}
            properties[field_name] = schema
            if binding.required and not binding.has_default:
                required.append(field_name)
        payload: dict[str, Any] = {
            "title": cls.__name__,
            "type": "object",
            "properties": properties,
        }
        if required:
            payload["required"] = required
        return payload

    async def save(self) -> BaseMarshall:
        model = cast("type[Model]", self.marshall_config["model"])
        if self._setup_used:
            instance = await self.instance.save()
        else:
            data = {
                field_name: getattr(self, field_name)
                for field_name in self._explicit_fields
                if field_name in model.fields
                and not (
                    model.fields[field_name].primary_key and model.fields[field_name].autoincrement
                )
            }
            instance = await self.instance.save(values=data)

        self._handle_primary_key(instance)
        return self


def _annotation_to_schema(annotation: Any) -> dict[str, Any]:
    origin = get_origin(annotation)
    if origin is typing.Union:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return _annotation_to_schema(args[0])
        return {"anyOf": [_annotation_to_schema(arg) for arg in args]}
    if origin in (list, set, tuple):
        return {"type": "array"}
    if origin is dict:
        return {"type": "object"}
    if annotation in (str,):
        return {"type": "string"}
    if annotation in (int,):
        return {"type": "integer"}
    if annotation in (float,):
        return {"type": "number"}
    if annotation in (bool,):
        return {"type": "boolean"}
    if annotation in (bytes, bytearray):
        return {"type": "string", "format": "byte"}
    return {}


class Marshall(BaseMarshall, metaclass=MarshallMeta):
    context: dict[str, Any]

    async def save(self) -> Marshall:
        return cast("Marshall", await super().save())

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self}>"

    def __str__(self) -> str:
        model = cast("type[Model]", self.marshall_config["model"])
        return f"{type(self).__name__}({model.__name__})"


__all__ = ["BaseMarshall", "Marshall"]
