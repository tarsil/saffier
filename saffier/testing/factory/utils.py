from __future__ import annotations

from collections.abc import Callable, Collection
from inspect import isclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from saffier.core.db.fields.base import BaseFieldType
    from saffier.core.db.models.model import Model

    from .fields import FactoryField
    from .types import FactoryCallback, FactoryParameterCallback, ModelFactoryContext


EDGY_FIELD_PARAMETERS: dict[
    str, tuple[str, Callable[[BaseFieldType, str, ModelFactoryContext], Any]]
] = {
    "ge": ("min", lambda field, attr_name, context: getattr(field, attr_name)),
    "le": ("max", lambda field, attr_name, context: getattr(field, attr_name)),
    "multiple_of": ("step", lambda field, attr_name, context: getattr(field, attr_name)),
    "decimal_places": (
        "right_digits",
        lambda field, attr_name, context: getattr(field, attr_name),
    ),
}


def remove_unparametrized_relationship_fields(
    model: type[Model],
    kwargs: dict[str, Any],
    extra_exclude: Collection[str | Literal[False]] = (),
) -> None:
    parameters: dict[str, dict[str, Any]] = kwargs.get("parameters") or {}
    excluded: set[str | Literal[False]] = {*(kwargs.get("exclude") or []), *extra_exclude}
    excluded.discard(False)

    relationship_fields = set(getattr(model.meta, "foreign_key_fields", {}))
    relationship_fields.update(
        getattr(getattr(model.meta, "many_to_many_fields", set()), "keys", lambda: [])()
    )

    for field_name in relationship_fields:
        field = model.meta.fields[field_name]
        if field_name not in parameters and field.has_default():
            excluded.add(field_name)

    kwargs["exclude"] = excluded


def edgy_field_param_extractor(
    factory_fn: FactoryCallback | str,
    *,
    remapping: dict[
        str,
        tuple[str, Callable[[BaseFieldType, str, ModelFactoryContext], Any]] | None,
    ]
    | None = None,
    defaults: dict[str, Any | FactoryParameterCallback] | None = None,
) -> FactoryCallback:
    remapping = remapping or {}
    remapping = {**EDGY_FIELD_PARAMETERS, **remapping}

    if isinstance(factory_fn, str):
        factory_name = factory_fn
        factory_fn = lambda field, context, kwargs: getattr(context["faker"], factory_name)(  # noqa: E731
            **kwargs
        )

    def mapper_fn(
        field: FactoryField, context: ModelFactoryContext, kwargs: dict[str, Any]
    ) -> Any:
        db_field = field.owner.meta.model.meta.fields[field.name]

        for attr, mapper in remapping.items():
            if mapper is None:
                continue
            if getattr(db_field, attr, None) is not None:
                kwargs.setdefault(mapper[0], mapper[1](db_field, attr, context))

        if defaults:
            for name, value in defaults.items():
                if name not in kwargs:
                    if callable(value) and not isclass(value):
                        value = value(field, context, name)
                    kwargs[name] = value

        return factory_fn(field, context, kwargs)

    return mapper_fn


def default_wrapper(
    factory_fn: FactoryCallback | str,
    defaults: dict[str, Any],
) -> FactoryCallback:
    if isinstance(factory_fn, str):
        factory_name = factory_fn
        factory_fn = lambda field, context, kwargs: getattr(context["faker"], factory_name)(  # noqa: E731
            **kwargs
        )

    def mapper_fn(
        field: FactoryField, context: ModelFactoryContext, kwargs: dict[str, Any]
    ) -> Any:
        for name, value in defaults.items():
            if name not in kwargs:
                if callable(value) and not isclass(value):
                    value = value(field, context, name)
                kwargs[name] = value
        return factory_fn(field, context, kwargs)

    return mapper_fn
