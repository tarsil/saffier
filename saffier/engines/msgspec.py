"""msgspec-backed model engine adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from saffier.engines.base import EngineIncludeExclude, ModelEngine
from saffier.engines.utils import optional_annotation, resolve_annotation, saffier_field_annotation
from saffier.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    from saffier.core.db.models.model import Model


class MsgspecModelEngine(ModelEngine):
    """msgspec-backed adapter that projects Saffier models into `Struct` types.

    The adapter keeps Saffier in charge of persistence and queryset behavior
    while using msgspec for typed validation, JSON schema generation, and
    serialization.
    """

    name = "msgspec"

    def __init__(
        self,
        *,
        strict: bool = False,
        struct_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the adapter.

        Args:
            strict: Whether validation should use msgspec strict conversion
                rules.
            struct_config: Extra keyword arguments forwarded to
                `msgspec.defstruct()`.
        """
        self.strict = strict
        self.struct_config = dict(struct_config or {})
        self._model_cache: dict[tuple[type[Model], str, int], type[Any]] = {}

    def _import_msgspec(self) -> Any:
        """Import and return the msgspec module lazily."""
        try:
            import msgspec
        except ImportError as exc:  # pragma: no cover
            raise ImproperlyConfigured(
                "The 'msgspec' model engine requires the 'msgspec' package to be installed."
            ) from exc
        return msgspec

    def _field_definition(
        self,
        field_name: str,
        field: Any,
        model_class: type[Model],
        *,
        mode: str,
    ) -> tuple[Any, ...]:
        """Build one msgspec struct field definition from a Saffier field."""
        msgspec = self._import_msgspec()
        annotation = saffier_field_annotation(field, model_class)

        if mode == "projection":
            return (field_name, optional_annotation(annotation), None)

        if getattr(field, "is_computed", False):
            return (field_name, optional_annotation(annotation), None)
        if getattr(field, "primary_key", False) and getattr(field, "autoincrement", False):
            return (field_name, optional_annotation(annotation), None)
        if getattr(field.validator, "read_only", False):
            return (field_name, optional_annotation(annotation), None)
        if getattr(field, "server_default", None) is not None:
            return (field_name, optional_annotation(annotation), None)
        if getattr(field, "null", False):
            return (field_name, optional_annotation(annotation), None)
        if field.validator.has_default():
            default = getattr(field.validator, "default", None)
            if callable(default):
                return (
                    field_name,
                    annotation,
                    msgspec.field(default_factory=default),
                )
            return (field_name, annotation, default)
        return (field_name, annotation)

    def _plain_field_definition(
        self,
        field_name: str,
        plain_field: dict[str, Any],
        model_class: type[Model],
        *,
        mode: str,
    ) -> tuple[Any, ...]:
        """Build one msgspec struct field definition from a plain field."""
        annotation = optional_annotation(
            resolve_annotation(plain_field.get("annotation", Any), model_class)
        )
        default = plain_field.get("default")
        if mode == "projection":
            return (field_name, annotation, default)
        return (field_name, annotation, default)

    def _struct_to_data(
        self,
        struct_value: Any,
        *,
        only_fields: set[str] | None = None,
        exclude_none: bool = False,
    ) -> dict[str, Any]:
        """Convert one msgspec struct into a dictionary payload.

        Args:
            struct_value: msgspec struct instance.
            only_fields: Optional explicit field subset to preserve even when a
                field equals its declared default.
            exclude_none: Whether `None` values should be omitted.

        Returns:
            dict[str, Any]: Converted dictionary payload.
        """
        msgspec = self._import_msgspec()
        builtin_payload = cast("dict[str, Any]", msgspec.to_builtins(struct_value))

        if only_fields is None:
            field_names = tuple(getattr(type(struct_value), "__struct_fields__", ()))
        else:
            field_names = tuple(only_fields)

        payload: dict[str, Any] = {}
        for field_name in field_names:
            if field_name in builtin_payload:
                value = builtin_payload[field_name]
            else:
                value = getattr(struct_value, field_name)
            if exclude_none and value is None:
                continue
            payload[field_name] = value
        return payload

    def get_model_class(self, model_class: type[Model], *, mode: str = "projection") -> type[Any]:
        """Return the msgspec struct type for one Saffier model."""
        msgspec = self._import_msgspec()
        cache_key = (model_class, mode, getattr(model_class.meta, "_engine_generation", 0))
        if cache_key in self._model_cache:
            return self._model_cache[cache_key]

        fields: list[tuple[Any, ...]] = []
        for field_name, field in model_class.fields.items():
            if field.__class__.__name__ == "ManyToManyField":
                continue
            if mode == "projection" and getattr(field, "exclude", False):
                continue
            fields.append(self._field_definition(field_name, field, model_class, mode=mode))

        for field_name, plain_field in model_class.get_plain_model_fields().items():
            fields.append(
                self._plain_field_definition(field_name, plain_field, model_class, mode=mode)
            )

        namespace = {
            "__doc__": (
                f"msgspec {mode} model generated for the Saffier model '{model_class.__name__}'."
            )
        }
        engine_model = msgspec.defstruct(
            f"{model_class.__name__}{mode.capitalize()}EngineModel",
            fields,
            bases=(msgspec.Struct,),
            module=model_class.__module__,
            namespace=namespace,
            omit_defaults=True,
            forbid_unknown_fields=(mode == "validation"),
            kw_only=True,
            **self.struct_config,
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
        """Validate or coerce a value into the msgspec struct representation."""
        msgspec = self._import_msgspec()
        engine_model = self.get_model_class(model_class, mode=mode)
        if isinstance(value, engine_model):
            return value
        if hasattr(value, "__db_model__"):
            value = self.build_projection_payload(cast("Model", value))
        return msgspec.convert(
            value,
            type=engine_model,
            strict=self.strict if mode == "validation" else False,
            from_attributes=True,
            str_keys=True,
        )

    def to_saffier_data(
        self,
        model_class: type[Model],
        value: Any,
        *,
        exclude_unset: bool = False,
    ) -> dict[str, Any]:
        """Convert a msgspec value back into a Saffier constructor payload."""
        validated = self.validate_model(model_class, value, mode="validation")
        if exclude_unset and isinstance(value, Mapping):
            return self._struct_to_data(validated, only_fields=set(value.keys()))
        if exclude_unset:
            msgspec = self._import_msgspec()
            return cast("dict[str, Any]", msgspec.to_builtins(validated))
        return self._struct_to_data(validated)

    def dump_model(
        self,
        instance: Model,
        *,
        include: EngineIncludeExclude = None,
        exclude: EngineIncludeExclude = None,
        exclude_none: bool = False,
    ) -> dict[str, Any]:
        """Serialize one projected msgspec model back into a dictionary."""
        projection_payload = self.build_projection_payload(
            instance,
            include=include,
            exclude=exclude,
            exclude_none=exclude_none,
        )
        projected = self.validate_model(type(instance), projection_payload, mode="projection")
        return self._struct_to_data(
            projected,
            only_fields=set(projection_payload.keys()),
            exclude_none=exclude_none,
        )

    def dump_model_json(
        self,
        instance: Model,
        *,
        include: EngineIncludeExclude = None,
        exclude: EngineIncludeExclude = None,
        exclude_none: bool = False,
    ) -> str:
        """Serialize one projected msgspec model into JSON."""
        msgspec = self._import_msgspec()
        return cast(
            "bytes",
            msgspec.json.encode(
                self.dump_model(
                    instance,
                    include=include,
                    exclude=exclude,
                    exclude_none=exclude_none,
                )
            ),
        ).decode("utf-8")

    def json_schema(
        self,
        model_class: type[Model],
        *,
        mode: str = "projection",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return the msgspec-generated JSON schema for one model."""
        del kwargs
        msgspec = self._import_msgspec()
        return cast(
            "dict[str, Any]", msgspec.json.schema(self.get_model_class(model_class, mode=mode))
        )


__all__ = ["MsgspecModelEngine"]
