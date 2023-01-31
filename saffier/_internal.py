from optparse import NO_DEFAULT
from typing import Any, Dict, Union

from pydantic import BaseConfig, BaseModel
from pydantic.fields import FieldInfo, Undefined
from typesystem import Integer
from typesystem import Schema as ISchema

from saffier.types import DictAny

NO_DEFAULT = object()


class SaffierField(FieldInfo):
    def __init__(self, default: Any = NO_DEFAULT, **kwargs: Any) -> None:
        if default is not NO_DEFAULT:
            self.default = default
        super().__init__(default, **kwargs)

    def validate(self, value: Any) -> Any:
        if value is None and self.null:
            return None
        elif not isinstance(value, str):
            raise ValueError("Must be a string.")

        value = value.replace("\0", "")

        if self.min_length is not None:
            if len(value) < self.min_length:
                raise ValueError("Must have at least {min_length} characters.")

        if self.max_length is not None:
            if len(value) > self.max_length:
                raise ValueError("Must have no more than {max_length} characters.")
        return value

    def get_default_value(self) -> Any:
        default = getattr(self, "default", None)
        if callable(default):
            return default()
        return default


class AnyField(FieldInfo):
    """
    Always matches.
    """

    def validate(self, value: Any) -> Any:
        return value


class Schema(FieldInfo):
    """
    Schema representation of a Schema for Saffier
    """

    def __init__(
        self, default: Any = Undefined, *, fields: Dict[str, SaffierField], **kwargs: DictAny
    ) -> Any:
        kwargs.update(fields=fields)
        super().__init__(default=default, **kwargs)
        self.fields = fields

    class Config(BaseConfig):
        extra = "allow"
        arbitrary_types_allowed = True
