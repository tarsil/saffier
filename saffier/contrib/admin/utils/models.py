from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Literal, cast

import saffier

try:
    from lilya.context import session as _session
except ImportError:  # pragma: no cover
    _session = None

if TYPE_CHECKING:
    from saffier.core.db.models.model import Model

_recent_models_var: ContextVar[list[str] | None] = ContextVar(
    "_recent_admin_models",
    default=None,
)


class CallableDefaultJsonSchema:
    """Marker requesting callable defaults in generated admin JSON schema.

    Saffier's lightweight marshalling schema path does not depend on Pydantic's
    schema generator classes, but callers may still pass generator-like marker
    classes to choose callable-default behavior. This marker preserves that
    public switch without importing Pydantic at runtime.
    """

    include_callable_defaults = True


class NoCallableDefaultJsonSchema:
    """Marker requesting callable defaults to be omitted from admin schema.

    The model schema implementation checks this attribute when it receives a
    Pydantic-style ``schema_generator`` argument. Keeping the marker small makes
    the admin schema path independent from Pydantic while retaining the useful
    public switch.
    """

    include_callable_defaults = False


def get_registered_models() -> dict[str, type[Model]]:
    """Return models visible to the active Saffier admin instance.

    The helper mirrors ``AdminSite`` for legacy utility callers that do not have
    a site object. It reads the current Monkay instance, uses the registry's
    canonical ``admin_models`` membership set when available, and falls back to
    all registered models only for older registry objects.

    Returns:
        dict[str, type[Model]]: Registry names mapped to Saffier model classes.
        An empty dictionary is returned when no active instance exists.
    """
    instance = saffier.monkay.instance
    if instance is None:
        return {}
    registry = instance.registry
    admin_models = getattr(registry, "admin_models", None)
    if admin_models is not None:
        return {name: registry.get_model(name) for name in admin_models}
    return dict(registry.models)


def get_model(model_name: str, *, no_check_admin_models: bool = False) -> type[Model]:
    """Resolve a model by name from the active Saffier admin registry.

    Args:
        model_name: Registry name of the model to resolve.
        no_check_admin_models: When true, allow lookup outside the admin-visible
            model set. This is reserved for schema internals that need to resolve
            infrastructure models without making them browsable.

    Returns:
        type[Model]: Saffier model class.

    Raises:
        LookupError: If no active registry exists or the model is not available
        under the requested visibility rules.
    """
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
    """Generate the admin JSON schema for a model.

    This function is intentionally thin over ``Model.model_json_schema``. Saffier
    models own their admin marshalling schema, while this utility keeps a
    flexible call signature for tests, docs, and optional admin tooling.

    Args:
        model: Model class or registry name.
        mode: Schema mode passed to the model schema generator.
        phase: Admin marshalling phase such as ``"create"``, ``"update"``, or
            ``"view"``.
        include_callable_defaults: Whether callable defaults should be executed
            and included in the schema.
        no_check_admin_models: Whether to bypass admin visibility checks when
            resolving a model name.
        **kwargs: Additional compatibility arguments accepted by model schema
            generation.

    Returns:
        dict[str, Any]: JSON schema dictionary.
    """
    del kwargs
    if isinstance(model, str):
        model = get_model(model, no_check_admin_models=no_check_admin_models)

    return model.model_json_schema(
        mode=mode,
        phase=phase,
        include_callable_defaults=include_callable_defaults,
    )


def _get_session_recent_models() -> list[str] | None:
    """Return the active Lilya session recent-model list when available.

    Recent model navigation is a request-scoped admin convenience. Lilya session
    context provides the right persistence across redirects, but direct tests can
    call these helpers without a request, so absence of the context is handled by
    returning ``None``.

    Returns:
        list[str] | None: Mutable session-backed model-name list, or ``None``.
    """
    if _session is None:
        return None
    try:
        if not hasattr(_session, "recent_models"):
            _session.recent_models = []
        return cast("list[str]", _session.recent_models)
    except (LookupError, RuntimeError):
        return None


def add_to_recent_models(model: type[Model]) -> None:
    """Record a model as recently visited by the admin operator.

    The list is kept short and duplicate-free so the dashboard can show useful
    navigation without becoming another unbounded session store. The model name
    comes from the class display name because that is what the admin templates
    show to users.

    Args:
        model: Saffier model class that was just opened.
    """
    session_recent_models = _get_session_recent_models()
    source = (
        session_recent_models if session_recent_models is not None else _recent_models_var.get()
    )
    recent_models = [name for name in (source or [])[:10] if name != model.__name__]
    recent_models.insert(0, model.__name__)
    if session_recent_models is not None:
        session_recent_models[:] = recent_models
    else:
        _recent_models_var.set(recent_models)


def get_recent_models() -> list[str]:
    """Return the current recent-model navigation list.

    Returns:
        list[str]: Model display names, newest first. The list is empty when no
        model has been visited in the current admin workflow.
    """
    session_recent_models = _get_session_recent_models()
    if session_recent_models is not None:
        return list(session_recent_models)
    return list(_recent_models_var.get() or ())


__all__ = [
    "CallableDefaultJsonSchema",
    "NoCallableDefaultJsonSchema",
    "add_to_recent_models",
    "get_model",
    "get_model_json_schema",
    "get_recent_models",
    "get_registered_models",
]
