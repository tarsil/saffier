import decimal
import re
import typing
from math import isfinite
from optparse import NO_DEFAULT

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
    FieldInfo representation of a String
    """

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

        self.blank = blank
        self.trim_whitespace = trim_whitespace
        self.min_length = min_length
        self.max_length = max_length
        self.coerse_types = coerse_types
