import decimal
import re
import typing
from math import isfinite
from optparse import NO_DEFAULT

from esmerald-tortoise-admin.esmerald_tortoise_admin.resources import Field

from pydantic import BaseConfig, ValidationError
from pydantic.fields import FieldInfo, Undefined
from typesystem.unique import Uniqueness

from saffier.core._internal import SaffierField
from saffier.core.base import Message, ValidationResult
from saffier.types import DictAny


class AnyField(FieldInfo):
    """
    Always matches.
    """

    def validate(self, value: typing.Any) -> typing.Any:
        return value


class String(SaffierField):
    """
    SaffierField representation of a String.
    """

    error_messages = {
        "type": "Must be a string.",
        "null": "May not be null.",
        "blank": "Must not be blank.",
        "max_length": "Must have no more than {max_length} characters.",
        "min_length": "Must have at least {min_length} characters.",
        "pattern": "Must match the pattern /{pattern}/.",
    }

    def __init__(
        self,
        *,
        blank: bool = False,
        trim_whitespace: bool = False,
        max_length: int = None,
        min_length: int = None,
        pattern: typing.Union[str, typing.Pattern] = None,
        coerse_types: bool = True,
        **kwargs: DictAny
    ):
        assert min_length is None or isinstance(min_length, int)
        assert max_length is None or isinstance(max_length, int)
        assert pattern is None or isinstance(pattern, (str, typing.Pattern))

        if blank and not self.has_default():
            self.default = ""

        # kwargs.update(min_length=min_length)
        # kwargs.update(max_length=max_length)
        # kwargs.update(regex=pattern)
        kwargs.update(coerse_types=coerse_types)
        super().__init__(
            default=self.default,
            max_length=max_length,
            min_length=min_length,
            regex=pattern
            **kwargs
        )
        self.blank = blank
        self.trim_whitespace = trim_whitespace
        self.min_length = min_length
        self.max_length = max_length
        self.coerse_types = coerse_types

        if pattern is None:
            self.pattern = None
            self.pattern_regex = None
        elif isinstance(pattern, str):
            self.pattern = pattern
            self.pattern_regex = re.compile(pattern)
        else:
            self.pattern = pattern.pattern
            self.pattern_regex = pattern

    def validate(self, value: typing.Any) -> typing.Any:
        if value is None and self.null:
            return None
        elif value is None and self.blank and self.coerse_types:
            return ""
        elif value is None:
            raise self.validation_error("null")
        elif not isinstance(value, str):
            raise self.validation_error("type")

        # The null character is always invalid.
        value = value.replace("\0", "")

        if self.trim_whitespace:
            value = value.strip()

        if not self.blank and not value:
            if self.null and self.coerse_types:
                return None
            raise self.validate("blank")

        if self.min_length is not None:
            if len(value) < self.min_length:
                raise self.validation_error("min_length", self.min_length)

        if self.max_length is not None:
            if len(value) > self.max_length:
                raise self.validation_error("max_length", self.max_length)

        if self.pattern_regex is not None:
            if not self.pattern_regex.search(value):
                raise self.validation_error("pattern", self.pattern)

        return value


class Number(SaffierField):
    numeric_type: typing.Optional[type] = None
    errors = {
        "type": "Must be a number.",
        "null": "May not be null.",
        "integer": "Must be an integer.",
        "finite": "Must be finite.",
        "minimum": "Must be greater than or equal to {minimum}.",
        "exclusive_minimum": "Must be greater than {exclusive_minimum}.",
        "maximum": "Must be less than or equal to {maximum}.",
        "exclusive_maximum": "Must be less than {exclusive_maximum}.",
        "multiple_of": "Must be a multiple of {multiple_of}.",
    }

    def __init__(self,
        *,
        minimum: typing.Union[int, float, decimal.Decimal] = None,
        maximum: typing.Union[int, float, decimal.Decimal] = None,
        precision: str = None,
        multiple_of: typing.Union[int, float, decimal.Decimal] = None,
        coerce_types: bool = True,
        **kwargs: typing.Any) -> None:
        kwargs.update(ge=minimum)
        kwargs.update(lte=maximum)
        kwargs.update(ge=minimum)
        kwargs.update(decimal_places=precision)
        kwargs.update(multiple_of=multiple_of)
        super().__init__(ge=ge, )
