import typing
from enum import Enum

from orjson import OPT_OMIT_MICROSECONDS  # noqa
from orjson import OPT_SERIALIZE_NUMPY  # noqa
from orjson import dumps

from saffier.fields import DateField, DateTimeField
from saffier.types import DictAny


class ModelUtil:
    """
    Utils used by the Registry
    """

    def _update_auto_now_fields(self, values: DictAny, fields: DictAny) -> DictAny:
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
