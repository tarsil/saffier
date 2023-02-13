import typing
from inspect import isclass

from typing_extensions import get_origin

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
                values[k] = v.validator.get_default_value()
        return values


def is_class_and_subclass(value: typing.Any, _type: typing.Any) -> bool:
    original = get_origin(value)
    if not original and not isclass(value):
        return False

    try:
        if original:
            return original and issubclass(original, _type)
        return issubclass(value, _type)
    except TypeError:
        return False
