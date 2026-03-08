"""Core engine adapter interfaces and registration helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, TypeAlias, cast

import orjson

from saffier.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    from saffier.core.db.models.model import Model


EngineIncludeExclude: TypeAlias = set[int] | set[str] | dict[int, Any] | dict[str, Any] | None


class ModelEngine(ABC):
    """Base class for optional model-engine adapters layered on top of Saffier.

    Concrete adapters expose external model representations such as Pydantic or
    msgspec while keeping Saffier's own model lifecycle as the source of truth.
    """

    name: str = ""

    @staticmethod
    def _is_included(field_name: str, include: EngineIncludeExclude) -> bool:
        """Return whether one field should be kept by an include rule."""
        if include is None:
            return True
        if isinstance(include, dict):
            return field_name in include and include[field_name] is not False
        return field_name in include

    @staticmethod
    def _is_excluded(field_name: str, exclude: EngineIncludeExclude) -> bool:
        """Return whether one field should be removed by an exclude rule."""
        if exclude is None:
            return False
        if isinstance(exclude, dict):
            return exclude.get(field_name) is True
        return field_name in exclude

    def build_projection_payload(
        self,
        instance: Model,
        *,
        include: EngineIncludeExclude = None,
        exclude: EngineIncludeExclude = None,
        exclude_none: bool = False,
    ) -> dict[str, Any]:
        """Build the Saffier-owned payload used to project one instance.

        Args:
            instance: Source Saffier model instance.
            include: Optional nested include rules.
            exclude: Optional nested exclude rules.
            exclude_none: Whether `None` values should be omitted.

        Returns:
            dict[str, Any]: Payload containing Saffier field data plus any
            declared plain Python fields.
        """
        payload = instance.model_dump(include=include, exclude=exclude, exclude_none=exclude_none)

        for field_name in type(instance).get_plain_model_fields():
            if not self._is_included(field_name, include) or self._is_excluded(
                field_name, exclude
            ):
                continue
            if field_name not in instance.__dict__:
                continue
            value = instance.__dict__[field_name]
            if exclude_none and value is None:
                continue
            payload[field_name] = value
        return payload

    def project_model(
        self,
        instance: Model,
        *,
        include: EngineIncludeExclude = None,
        exclude: EngineIncludeExclude = None,
        exclude_none: bool = False,
    ) -> Any:
        """Project one Saffier model instance into the engine representation."""
        payload = self.build_projection_payload(
            instance,
            include=include,
            exclude=exclude,
            exclude_none=exclude_none,
        )
        return self.validate_model(type(instance), payload, mode="projection")

    def dump_model(
        self,
        instance: Model,
        *,
        include: EngineIncludeExclude = None,
        exclude: EngineIncludeExclude = None,
        exclude_none: bool = False,
    ) -> dict[str, Any]:
        """Serialize one projected engine model back into a plain dictionary."""
        projected = self.project_model(
            instance,
            include=include,
            exclude=exclude,
            exclude_none=exclude_none,
        )
        if isinstance(projected, Mapping):
            return dict(projected)

        dump = getattr(projected, "model_dump", None)
        if callable(dump):
            kwargs: dict[str, Any] = {"exclude_unset": True, "exclude_none": exclude_none}
            if include is not None:
                kwargs["include"] = include
            if exclude is not None:
                kwargs["exclude"] = exclude
            try:
                return cast("dict[str, Any]", dump(**kwargs))
            except TypeError:
                kwargs.pop("exclude_unset", None)
                return cast("dict[str, Any]", dump(**kwargs))

        if hasattr(projected, "__dict__"):
            payload = {
                key: value
                for key, value in projected.__dict__.items()
                if not key.startswith("_")
                and self._is_included(key, include)
                and not self._is_excluded(key, exclude)
            }
            if exclude_none:
                payload = {key: value for key, value in payload.items() if value is not None}
            return payload

        raise TypeError(
            f"Engine '{self.name}' returned '{type(projected).__name__}' without a dump interface."
        )

    def dump_model_json(
        self,
        instance: Model,
        *,
        include: EngineIncludeExclude = None,
        exclude: EngineIncludeExclude = None,
        exclude_none: bool = False,
    ) -> str:
        """Serialize one projected engine model into JSON."""
        projected = self.project_model(
            instance,
            include=include,
            exclude=exclude,
            exclude_none=exclude_none,
        )
        dump_json = getattr(projected, "model_dump_json", None)
        if callable(dump_json):
            kwargs: dict[str, Any] = {"exclude_unset": True, "exclude_none": exclude_none}
            if include is not None:
                kwargs["include"] = include
            if exclude is not None:
                kwargs["exclude"] = exclude
            try:
                return cast("str", dump_json(**kwargs))
            except TypeError:
                kwargs.pop("exclude_unset", None)
                return cast("str", dump_json(**kwargs))

        return orjson.dumps(
            self.dump_model(
                instance,
                include=include,
                exclude=exclude,
                exclude_none=exclude_none,
            ),
            option=orjson.OPT_NON_STR_KEYS,
        ).decode("utf-8")

    @abstractmethod
    def get_model_class(self, model_class: type[Model], *, mode: str = "projection") -> type[Any]:
        """Return the engine-backed representation class for one Saffier model."""

    @abstractmethod
    def validate_model(
        self,
        model_class: type[Model],
        value: Any,
        *,
        mode: str = "validation",
    ) -> Any:
        """Validate or coerce `value` into the engine-backed representation."""

    @abstractmethod
    def to_saffier_data(
        self,
        model_class: type[Model],
        value: Any,
        *,
        exclude_unset: bool = False,
    ) -> dict[str, Any]:
        """Convert an engine-backed value back into Saffier constructor data."""

    @abstractmethod
    def json_schema(
        self,
        model_class: type[Model],
        *,
        mode: str = "projection",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return an engine-generated schema for the Saffier model."""


ModelEngineFactory: TypeAlias = Callable[[], ModelEngine] | type[ModelEngine] | ModelEngine


def _ensure_model_engine_instance(configured: ModelEngineFactory) -> ModelEngine:
    """Normalize one engine registration entry into an adapter instance.

    Args:
        configured: Registered engine object, class, or factory.

    Returns:
        ModelEngine: Instantiated adapter.

    Raises:
        ImproperlyConfigured: If the configured object does not resolve to a
            valid `ModelEngine`.
    """
    if isinstance(configured, ModelEngine):
        engine = configured
    elif (
        isinstance(configured, type)
        and issubclass(configured, ModelEngine)
        or callable(configured)
    ):
        engine = configured()
    else:
        raise ImproperlyConfigured("Configured model engine is invalid.")

    if not isinstance(engine, ModelEngine):
        raise ImproperlyConfigured("Configured model engine must inherit from ModelEngine.")
    if not getattr(engine, "name", "").strip():
        raise ImproperlyConfigured("Configured model engine must define a non-empty 'name'.")
    return engine


class ModelEngineRegistry:
    """Global registry of named model-engine adapters."""

    def __init__(self) -> None:
        """Initialize the empty adapter registry."""
        self._registered: dict[str, ModelEngineFactory] = {}
        self._resolved: dict[str, ModelEngine] = {}

    def register(
        self,
        name: str | None,
        engine: ModelEngineFactory,
        *,
        overwrite: bool = False,
    ) -> ModelEngine:
        """Register one model-engine adapter under a stable name.

        Args:
            name: Adapter name. When omitted, the adapter instance's `name` is
                used.
            engine: Engine class, instance, or factory.
            overwrite: Whether an existing registration may be replaced.

        Returns:
            ModelEngine: Resolved adapter instance for the registered name.
        """
        resolved = _ensure_model_engine_instance(engine)
        engine_name = (name or resolved.name).strip()
        if not engine_name:
            raise ImproperlyConfigured("Model engine names cannot be empty.")
        if not overwrite and engine_name in self._registered:
            raise ImproperlyConfigured(f"Model engine '{engine_name}' is already registered.")
        self._registered[engine_name] = engine
        self._resolved.pop(engine_name, None)
        return self.get(engine_name)

    def get(self, name: str) -> ModelEngine:
        """Return one previously registered adapter by name."""
        engine_name = name.strip()
        if not engine_name:
            raise ImproperlyConfigured("Model engine names cannot be empty.")
        if engine_name in self._resolved:
            return self._resolved[engine_name]
        try:
            configured = self._registered[engine_name]
        except KeyError as exc:
            raise ImproperlyConfigured(f"Model engine '{engine_name}' is not registered.") from exc
        resolved = _ensure_model_engine_instance(configured)
        self._resolved[engine_name] = resolved
        return resolved


_MODEL_ENGINE_REGISTRY = ModelEngineRegistry()


def register_model_engine(
    name: str | None,
    engine: ModelEngineFactory,
    *,
    overwrite: bool = False,
) -> ModelEngine:
    """Register one model-engine adapter in the global registry."""
    return _MODEL_ENGINE_REGISTRY.register(name, engine, overwrite=overwrite)


def get_model_engine(name: str) -> ModelEngine:
    """Return one globally registered model-engine adapter."""
    return _MODEL_ENGINE_REGISTRY.get(name)


def resolve_model_engine(configured: str | ModelEngineFactory | None | bool) -> ModelEngine | None:
    """Resolve one model-engine configuration value.

    Args:
        configured: Configuration entry from a model or registry.

    Returns:
        ModelEngine | None: Resolved adapter, or `None` when engine support is
            disabled.
    """
    if configured in (None, False):
        return None
    if isinstance(configured, str):
        return get_model_engine(configured)
    return _ensure_model_engine_instance(configured)


__all__ = [
    "EngineIncludeExclude",
    "ModelEngine",
    "ModelEngineRegistry",
    "get_model_engine",
    "register_model_engine",
    "resolve_model_engine",
]
