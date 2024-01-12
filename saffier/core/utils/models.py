import typing
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, Type

from orjson import OPT_OMIT_MICROSECONDS  # noqa
from orjson import OPT_SERIALIZE_NUMPY  # noqa
from orjson import dumps

import saffier
from saffier.core.db.fields import DateField, DateTimeField

saffier_setattr = object.__setattr__

if TYPE_CHECKING:
    from saffier import Model
    from saffier.core.db.models.metaclasses import MetaInfo


class DateParser:
    """
    Utils used by the Registry
    """

    def _update_auto_now_fields(self, values: Any, fields: Any) -> Any:
        """
        Updates the auto fields
        """
        for k, v in fields.items():
            if isinstance(v, (DateField, DateTimeField)) and v.auto_now:
                values[k] = v.validator.get_default_value()  # type: ignore
        return values

    def _resolve_value(self, value: typing.Any) -> typing.Any:
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
    __definitions__: Optional[Dict[Any, Any]] = None,
    __metadata__: Optional[Type["MetaInfo"]] = None,
    __qualname__: Optional[str] = None,
    __bases__: Optional[Tuple[Type["Model"]]] = None,
    __proxy__: bool = False,
) -> Type["Model"]:
    """
    Generates an `saffier.Model` with all the required definitions to generate the pydantic
    like model.
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

    model: Type["Model"] = type(__name__, __bases__, core_definitions)
    return model


def generify_model_fields(model: Type["Model"]) -> Dict[Any, Any]:
    """
    Makes all fields generic when a partial model is generated or used.
    This also removes any metadata for the field such as validations making
    it a clean slate to be used internally to process dynamic data and removing
    the constraints of the original model fields.
    """
    fields = {}

    # handle the nested non existing results
    for name, field in model.fields.items():
        saffier_setattr(field, "annotation", Any)
        saffier_setattr(field, "null", True)
        fields[name] = field

    return fields
