"""Pydantic-backed model engine adapter."""

from __future__ import annotations

import typing
from typing import Any, cast

from saffier.engines.base import ModelEngine
from saffier.engines.utils import optional_annotation, resolve_annotation, saffier_field_annotation
from saffier.exceptions import ImproperlyConfigured

if typing.TYPE_CHECKING:
    from saffier.core.db.models.model import Model


class PydanticModelEngine(ModelEngine):
    """Pydantic-backed adapter that projects validated Saffier model payloads."""

    name = "pydantic"

    def __init__(self, *, config: dict[str, Any] | None = None) -> None:
        """Initialize the adapter with optional `ConfigDict` overrides."""
        self.config = dict(config or {})
        self._model_cache: dict[tuple[type[Model], str, int], type[Any]] = {}

    def _import_pydantic(self) -> tuple[Any, Any, Any, Any]:
        """Import and return the required Pydantic symbols lazily."""
        try:
            from pydantic import BaseModel, ConfigDict, Field, create_model
        except ImportError as exc:  # pragma: no cover
            raise ImproperlyConfigured(
                "The 'pydantic' model engine requires the 'pydantic' package to be installed."
            ) from exc
        return BaseModel, ConfigDict, Field, create_model

    def _field_definition(
        self,
        field_name: str,
        field: Any,
        model_class: type[Model],
        *,
        mode: str,
    ) -> tuple[Any, Any]:
        """Build one Pydantic field definition from a Saffier field."""
        _, _, pydantic_field, _ = self._import_pydantic()
        annotation = saffier_field_annotation(field, model_class)

        if mode == "projection":
            return optional_annotation(annotation), None

        if getattr(field, "is_computed", False):
            return optional_annotation(annotation), None
        if getattr(field, "primary_key", False) and getattr(field, "autoincrement", False):
            return optional_annotation(annotation), None
        if getattr(field.validator, "read_only", False):
            return optional_annotation(annotation), None
        if getattr(field, "server_default", None) is not None:
            return optional_annotation(annotation), None
        if getattr(field, "null", False):
            return optional_annotation(annotation), None
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
        """Build one Pydantic field definition from a plain Python field."""
        del field_name
        annotation = resolve_annotation(plain_field.get("annotation", Any), model_class)
        annotation = optional_annotation(annotation)
        default = plain_field.get("default")
        if mode == "projection":
            return annotation, default
        return annotation, default

    def get_model_class(self, model_class: type[Model], *, mode: str = "projection") -> type[Any]:
        """Return the Pydantic model class for one Saffier model."""
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
        """Validate or coerce a value into the Pydantic representation."""
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
        """Convert a Pydantic value back into a Saffier constructor payload."""
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
        """Return the Pydantic-generated JSON schema for one model."""
        engine_model = self.get_model_class(model_class, mode=mode)
        return cast("dict[str, Any]", engine_model.model_json_schema(**kwargs))


__all__ = ["PydanticModelEngine"]
