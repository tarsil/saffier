from __future__ import annotations

import datetime
import decimal
import ipaddress
import sys
import typing
import uuid
from typing import Any, cast, get_args, get_origin

from saffier.engines.base import ModelEngine
from saffier.exceptions import ImproperlyConfigured

if typing.TYPE_CHECKING:
    from saffier.core.db.fields.base import Field
    from saffier.core.db.models.model import Model


class PydanticModelEngine(ModelEngine):
    """Pydantic-backed adapter that projects validated Saffier model payloads."""

    name = "pydantic"

    def __init__(self, *, config: dict[str, Any] | None = None) -> None:
        self.config = dict(config or {})
        self._model_cache: dict[tuple[type[Model], str, int], type[Any]] = {}

    def _import_pydantic(self) -> tuple[Any, Any, Any]:
        try:
            from pydantic import BaseModel, ConfigDict, Field, create_model
        except ImportError as exc:  # pragma: no cover
            raise ImproperlyConfigured(
                "The 'pydantic' model engine requires the 'pydantic' package to be installed."
            ) from exc
        return BaseModel, ConfigDict, Field, create_model

    def _resolve_annotation(self, annotation: Any, model_class: type[Model]) -> Any:
        if not isinstance(annotation, str):
            return annotation

        module_name = getattr(model_class, "__module__", "")
        globalns = dict(sys.modules[module_name].__dict__) if module_name in sys.modules else {}
        localns = dict(model_class.__dict__)
        localns.setdefault("typing", typing)
        localns.setdefault("ClassVar", typing.ClassVar)

        try:
            return eval(annotation, globalns, localns)
        except Exception:
            return Any

    def _annotation_allows_none(self, annotation: Any) -> bool:
        origin = get_origin(annotation)
        if origin is typing.Union:
            return type(None) in get_args(annotation)
        return annotation is Any or annotation is type(None)

    def _optional_annotation(self, annotation: Any) -> Any:
        if annotation in (Any, typing.Any):
            return Any
        if self._annotation_allows_none(annotation):
            return annotation
        return annotation | None

    def _infer_field_type(self, field: Field) -> Any:
        if hasattr(field, "target"):
            return Any

        validator_name = field.validator.__class__.__name__
        if validator_name in {"String", "Email", "URL", "Password"}:
            return str
        if validator_name == "UUID":
            return uuid.UUID
        if validator_name == "Integer":
            return int
        if validator_name == "Float":
            return float
        if validator_name == "Decimal":
            return decimal.Decimal
        if validator_name == "Boolean":
            return bool
        if validator_name == "Binary":
            return bytes
        if validator_name == "Date":
            return datetime.date
        if validator_name == "Time":
            return datetime.time
        if validator_name == "DateTime":
            return datetime.datetime
        if validator_name == "Duration":
            return datetime.timedelta
        if validator_name == "IPAddress":
            return ipaddress.IPv4Address
        if validator_name == "JSON":
            return dict[str, Any]
        return Any

    def _field_annotation(self, field: Field, model_class: type[Model]) -> Any:
        annotation = getattr(field, "annotation", None)
        if annotation not in (None, Any):
            return self._resolve_annotation(annotation, model_class)
        return self._infer_field_type(field)

    def _field_definition(
        self,
        field_name: str,
        field: Field,
        model_class: type[Model],
        *,
        mode: str,
    ) -> tuple[Any, Any]:
        _, _, pydantic_field, _ = self._import_pydantic()
        annotation = self._field_annotation(field, model_class)

        if mode == "projection":
            return self._optional_annotation(annotation), None

        if getattr(field, "is_computed", False):
            return self._optional_annotation(annotation), None
        if getattr(field, "primary_key", False) and getattr(field, "autoincrement", False):
            return self._optional_annotation(annotation), None
        if getattr(field.validator, "read_only", False):
            return self._optional_annotation(annotation), None
        if getattr(field, "server_default", None) is not None:
            return self._optional_annotation(annotation), None
        if getattr(field, "null", False):
            return self._optional_annotation(annotation), None
        if field.validator.has_default():
            default = getattr(field.validator, "default", None)
            if callable(default):
                return annotation, pydantic_field(default_factory=default)
            return annotation, default
        return annotation, ...

    def _plain_field_definition(
        self,
        field_name: str,
        plain_field: dict[str, Any],
        model_class: type[Model],
        *,
        mode: str,
    ) -> tuple[Any, Any]:
        del field_name
        annotation = self._resolve_annotation(plain_field.get("annotation", Any), model_class)
        annotation = self._optional_annotation(annotation)
        default = plain_field.get("default")
        if mode == "projection":
            return annotation, default
        return annotation, default

    def get_model_class(self, model_class: type[Model], *, mode: str = "projection") -> type[Any]:
        _, config_dict, _, create_model = self._import_pydantic()
        cache_key = (model_class, mode, getattr(model_class.meta, "_engine_generation", 0))
        if cache_key in self._model_cache:
            return self._model_cache[cache_key]

        fields: dict[str, tuple[Any, Any]] = {}
        for field_name, field in model_class.fields.items():
            if field.__class__.__name__ == "ManyToManyField":
                continue
            if mode == "projection" and getattr(field, "exclude", False):
                continue
            fields[field_name] = self._field_definition(
                field_name,
                field,
                model_class,
                mode=mode,
            )

        for field_name, plain_field in model_class.get_plain_model_fields().items():
            fields[field_name] = self._plain_field_definition(
                field_name,
                plain_field,
                model_class,
                mode=mode,
            )

        config = config_dict(
            arbitrary_types_allowed=True,
            extra="forbid",
            from_attributes=True,
            populate_by_name=True,
            validate_assignment=(mode == "validation"),
            **self.config,
        )
        engine_model = create_model(
            f"{model_class.__name__}{mode.capitalize()}EngineModel",
            __config__=config,
            __module__=model_class.__module__,
            **fields,
        )
        self._model_cache[cache_key] = engine_model
        return engine_model

    def validate_model(
        self,
        model_class: type[Model],
        value: Any,
        *,
        mode: str = "validation",
    ) -> Any:
        engine_model = self.get_model_class(model_class, mode=mode)
        if isinstance(value, engine_model):
            return value
        if hasattr(value, "__db_model__"):
            value = self.build_projection_payload(cast("Model", value))
        return engine_model.model_validate(value)

    def to_saffier_data(
        self,
        model_class: type[Model],
        value: Any,
        *,
        exclude_unset: bool = False,
    ) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            kwargs = {"exclude_unset": exclude_unset}
            try:
                return cast("dict[str, Any]", value.model_dump(**kwargs))
            except TypeError:
                return cast("dict[str, Any]", value.model_dump())
        validated = self.validate_model(model_class, value, mode="validation")
        return cast("dict[str, Any]", validated.model_dump(exclude_unset=exclude_unset))

    def json_schema(
        self,
        model_class: type[Model],
        *,
        mode: str = "projection",
        **kwargs: Any,
    ) -> dict[str, Any]:
        engine_model = self.get_model_class(model_class, mode=mode)
        return cast("dict[str, Any]", engine_model.model_json_schema(**kwargs))


__all__ = ["PydanticModelEngine"]
