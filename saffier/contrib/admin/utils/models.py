from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Literal, cast

import saffier

if TYPE_CHECKING:
    from saffier.core.db.models.model import Model

_recent_models_var: ContextVar[list[str]] = ContextVar("_recent_admin_models", default=[])


class CallableDefaultJsonSchema:
    include_callable_defaults = True


class NoCallableDefaultJsonSchema:
    include_callable_defaults = False


def get_registered_models() -> dict[str, type[Model]]:
    instance = saffier.monkay.instance
    if instance is None:
        return {}
    registry = instance.registry
    admin_models = getattr(registry, "admin_models", None)
    models = registry.models
    if admin_models:
        return {name: registry.get_model(name) for name in admin_models}
    return dict(models)


def get_model(model_name: str, *, no_check_admin_models: bool = False) -> type[Model]:
    models = get_registered_models()
    if not no_check_admin_models and model_name not in models:
        raise LookupError(model_name)
    if model_name in models:
        return cast("type[Model]", models[model_name])

    instance = saffier.monkay.instance
    if instance is None:
        raise LookupError(model_name)
    return cast("type[Model]", instance.registry.get_model(model_name))


def get_model_json_schema(
    model: str | type[Model],
    /,
    mode: Literal["validation", "serialization"] = "validation",
    phase: str = "view",
    include_callable_defaults: bool = False,
    no_check_admin_models: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    del kwargs
    if isinstance(model, str):
        model = get_model(model, no_check_admin_models=no_check_admin_models)

    return model.model_json_schema(
        mode=mode,
        phase=phase,
        include_callable_defaults=include_callable_defaults,
    )


def add_to_recent_models(model: type[Model]) -> None:
    recent_models = [name for name in _recent_models_var.get()[:10] if name != model.__name__]
    recent_models.insert(0, model.__name__)
    _recent_models_var.set(recent_models)


def get_recent_models() -> list[str]:
    return list(_recent_models_var.get())


__all__ = [
    "CallableDefaultJsonSchema",
    "NoCallableDefaultJsonSchema",
    "add_to_recent_models",
    "get_model",
    "get_model_json_schema",
    "get_recent_models",
    "get_registered_models",
]
