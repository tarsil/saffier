from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Any

from saffier.testing.exceptions import ExcludeValue


def _exclude_value(field: Any, context: dict[str, Any], parameters: dict[str, Any]) -> Any:
    raise ExcludeValue()


def _choice_value(field: Any, context: dict[str, Any], _: dict[str, Any]) -> Any:
    db_field = field.owner.meta.model.fields[field.name]
    choices = getattr(db_field, "choices", None)
    if not choices:
        raise ExcludeValue()
    if hasattr(choices, "__members__"):
        return context["faker"].random_element(elements=list(choices))
    values = []
    for choice in choices:
        if isinstance(choice, (tuple, list)):
            values.append(choice[0])
        else:
            values.append(choice)
    return context["faker"].random_element(elements=values)


def _duration_value(field: Any, context: dict[str, Any], _: dict[str, Any]) -> datetime.timedelta:
    return datetime.timedelta(seconds=context["faker"].pyint(min_value=0, max_value=3600))


def _array_value(field: Any, context: dict[str, Any], parameters: dict[str, Any]) -> list[str]:
    count = parameters.get("count", 3)
    return [context["faker"].word() for _ in range(count)]


DEFAULT_MAPPING: dict[str, Any] = {
    "BigIntegerField": lambda f, c, p: c["faker"].pyint(min_value=1, max_value=10_000),
    "SmallIntegerField": lambda f, c, p: c["faker"].pyint(min_value=0, max_value=100),
    "IntegerField": lambda f, c, p: c["faker"].pyint(min_value=1, max_value=1000),
    "FloatField": lambda f, c, p: c["faker"].pyfloat(left_digits=2, right_digits=2, positive=True),
    "DecimalField": lambda f, c, p: decimal.Decimal(
        str(c["faker"].pyfloat(min_value=1, max_value=100))
    ),
    "BooleanField": lambda f, c, p: c["faker"].pybool(),
    "CharField": lambda f, c, p: c["faker"].word(),
    "TextField": lambda f, c, p: c["faker"].sentence(),
    "ChoiceField": _choice_value,
    "CharChoiceField": _choice_value,
    "DateField": lambda f, c, p: c["faker"].date_object(),
    "DateTimeField": lambda f, c, p: c["faker"].date_time(),
    "TimeField": lambda f, c, p: c["faker"].time_object(),
    "DurationField": _duration_value,
    "EmailField": lambda f, c, p: c["faker"].email(),
    "URLField": lambda f, c, p: c["faker"].url(),
    "IPAddressField": lambda f, c, p: c["faker"].ipv4(),
    "PasswordField": lambda f, c, p: c["faker"].password(),
    "UUIDField": lambda f, c, p: uuid.uuid4(),
    "BinaryField": lambda f, c, p: c["faker"].binary(length=8),
    "JSONField": lambda f, c, p: {"value": c["faker"].word()},
    "FileField": lambda f, c, p: f"files/{c['faker'].uuid4()}.bin",
    "ImageField": lambda f, c, p: f"images/{c['faker'].uuid4()}.png",
    "PGArrayField": _array_value,
    # relationship-like fields default to ExcludeValue unless explicitly provided.
    "ForeignKey": _exclude_value,
    "OneToOneField": _exclude_value,
    "ManyToManyField": lambda f, c, p: [],
    "ExcludeField": _exclude_value,
    "PlaceholderField": _exclude_value,
    "ComputedField": _exclude_value,
}
