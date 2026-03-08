import typing
from enum import Enum
from typing import TYPE_CHECKING, Any

from orjson import (
    OPT_OMIT_MICROSECONDS,  # noqa
    OPT_SERIALIZE_NUMPY,  # noqa
    dumps,
)

import saffier
from saffier.core.db.fields import DateField, DateTimeField

saffier_setattr = object.__setattr__

if TYPE_CHECKING:
    from saffier import Model
    from saffier.core.db.models.metaclasses import MetaInfo


class DateParser:
    """Shared helpers for dynamic model payload normalization.

    The mixin is used by runtime model-generation paths that need to update
    timestamp fields automatically and serialize non-primitive Python values
    before they are handed to lower-level query builders.
    """

    def _update_auto_now_fields(self, values: Any, fields: Any) -> Any:
        """Refresh `auto_now` date and datetime fields inside a payload.

        Returns:
            Any: Updated payload dictionary.
        """
        for k, v in fields.items():
            if isinstance(v, (DateField, DateTimeField)) and v.auto_now:
                values[k] = v.validator.get_default_value()  # type: ignore
        return values

    def _resolve_value(self, value: typing.Any) -> typing.Any:
        """Normalize one value for storage or query generation.

        Dictionaries are JSON-encoded, enums are converted to their member
        names, and every other value is returned unchanged.

        Args:
            value (typing.Any): Raw value supplied by model or queryset code.

        Returns:
            typing.Any: Normalized value suitable for downstream processing.
        """
        if isinstance(value, dict):
            return dumps(
                value,
                option=OPT_SERIALIZE_NUMPY | OPT_OMIT_MICROSECONDS,
            ).decode("utf-8")
        elif isinstance(value, Enum):
            return value.name
        return value


def create_saffier_model(
    __name__: str,
    __module__: str,
    __definitions__: dict[Any, Any] | None = None,
    __metadata__: type["MetaInfo"] | None = None,
    __qualname__: str | None = None,
    __bases__: tuple[type["Model"]] | None = None,
    __proxy__: bool = False,
) -> type["Model"]:
    """Generate a dynamic Saffier model class.

    This helper is used by registry copying, reflection, proxy-model generation,
    and other runtime features that need to synthesize model classes from a
    field-definition payload.
    """

    if not __bases__:
        __bases__ = (saffier.Model,)

    qualname = __qualname__ or __name__
    core_definitions = {
        "__module__": __module__,
        "__qualname__": qualname,
        "is_proxy_model": __proxy__,
    }
    if not __definitions__:
        __definitions__ = {}

    core_definitions.update(**__definitions__)

    if __metadata__:
        core_definitions.update(**{"Meta": __metadata__})

    model: type[Model] = type(__name__, __bases__, core_definitions)
    return model


def generify_model_fields(model: type["Model"]) -> dict[Any, Any]:
    """Relax one model's field definitions for dynamic partial-model use.

    Proxy and partial-model generation paths need field objects that accept
    missing values and arbitrary payload shapes. This helper mutates the copied
    field definitions so every field becomes nullable and annotation-free before
    the temporary model class is assembled.

    Args:
        model (type[Model]): Model whose field definitions should be loosened.

    Returns:
        dict[Any, Any]: Mutated field mapping ready for temporary model
        generation.
    """
    fields = {}

    # handle the nested non existing results
    for name, field in model.fields.items():
        saffier_setattr(field, "annotation", Any)
        saffier_setattr(field, "null", True)
        fields[name] = field

    return fields
