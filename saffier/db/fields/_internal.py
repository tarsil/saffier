import decimal
import re
import typing
from math import isfinite

from saffier.core import formats
from saffier.core.base import ValidationResult
from saffier.core.datastructures import ArbitraryHashableBaseModel
from saffier.core.unique import Uniqueness
from saffier.exceptions import ValidationError

FORMATS = {
    "date": formats.DateFormat(),
    "time": formats.TimeFormat(),
    "datetime": formats.DateTimeFormat(),
    "uuid": formats.UUIDFormat(),
    "email": formats.EmailFormat(),
    "ipaddress": formats.IPAddressFormat(),
    "url": formats.URLFormat(),
}

NO_DEFAULT = object()


class SaffierField(ArbitraryHashableBaseModel):
    """
    The base of all fields used by Saffier
    """

    error_messages: typing.Dict[str, str] = {}

    def __init__(
        self,
        *,
        title: str = "",
        description: str = "",
        help_text: str = "",
        default: typing.Any = NO_DEFAULT,
        null: bool = False,
        read_only: bool = False,
        **kwargs: typing.Any,
    ) -> None:
        super().__init__(**kwargs)
        if null and default is NO_DEFAULT:
            default = None

        if default is not NO_DEFAULT:
            self.default = default

        self.null = null
        self.read_only = read_only
        self.title = title
        self.description = description
        self.help_text = help_text

    def check(self, value: typing.Any) -> typing.Any:
        raise NotImplementedError()  # pragma: no cover

    def validate_or_error(self, value: typing.Any) -> ValidationResult:
        try:
            value = self.check(value)
        except ValidationError as error:
            return ValidationResult(value=None, error=error)
        return ValidationResult(value=value, error=None)

    def has_default(self) -> bool:
        return hasattr(self, "default")

    def validation_error(
        self, code: str, value: typing.Optional[typing.Any] = None
    ) -> ValidationError:
        text = self.get_error_message(code)
        return ValidationError(text=text, code=code)

    def get_error_message(self, code: str) -> str:
        return self.error_messages[code].format(**self.__dict__)

    def get_default_value(self) -> typing.Any:
        default = getattr(self, "default", None)
        if callable(default):
            return default()
        return default


class String(SaffierField):
    """
    SaffierField representation of a String.
    """

    error_messages: typing.Dict[str, str] = {
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
        max_length: typing.Optional[int] = None,
        min_length: typing.Optional[int] = None,
        pattern: typing.Optional[typing.Union[str, typing.Pattern]] = None,
        format: typing.Optional[str] = None,
        coerse_types: bool = True,
        **kwargs: typing.Any,
    ):
        assert min_length is None or isinstance(min_length, int)
        assert max_length is None or isinstance(max_length, int)
        assert pattern is None or isinstance(pattern, (str, typing.Pattern))

        super().__init__(**kwargs)
        self.blank = blank
        self.trim_whitespace = trim_whitespace
        self.min_length = min_length
        self.max_length = max_length
        self.coerse_types = coerse_types
        self.format = format

        if blank and not self.has_default():
            self.default = ""

        if pattern is None:
            self.pattern = None
            self.pattern_regex = None
        elif isinstance(pattern, str):
            self.pattern = pattern
            self.pattern_regex = re.compile(pattern)
        else:
            self.pattern = pattern.pattern
            self.pattern_regex = pattern

    def check(self, value: typing.Any) -> typing.Any:
        if value is None and self.null:
            return None
        elif value is None and self.blank and self.coerse_types:
            return ""
        elif value is None:
            raise self.validation_error("null")
        elif self.format in FORMATS and FORMATS[self.format].is_native_type(value):
            return value
        elif not isinstance(value, str):
            raise self.validation_error("type")

        value = value.replace("\0", "")

        if self.trim_whitespace:
            value = value.strip()

        if not self.blank and not value:
            if self.null and self.coerse_types:
                return None
            raise self.check("blank")

        if self.min_length is not None:
            if len(value) < self.min_length:
                raise self.validation_error("min_length", self.min_length)

        if self.max_length is not None:
            if len(value) > self.max_length:
                raise self.validation_error("max_length", self.max_length)

        if self.pattern_regex is not None:
            if not self.pattern_regex.search(value):
                raise self.validation_error("pattern", self.pattern)

        if self.format in FORMATS:
            return FORMATS[self.format].check(value)

        return value


class Number(SaffierField):
    field_type: typing.Any = None
    error_messages: typing.Dict[str, str] = {
        "type": "Must be a number.",
        "null": "May not be null.",
        "integer": "Must be an integer.",
        "finite": "Must be finite.",
        "minimum": "Must be greater than or equal to {minimum}.",
        "exclusive_min": "Must be greater than {exclusive_minimum}.",
        "maximum": "Must be less than or equal to {maximum}.",
        "exclusive_max": "Must be less than {exclusive_maximum}.",
        "multiple_of": "Must be a multiple of {multiple_of}.",
    }

    def __init__(
        self,
        *,
        minimum: typing.Optional[typing.Union[int, float, decimal.Decimal]] = None,
        maximum: typing.Optional[typing.Union[int, float, decimal.Decimal]] = None,
        exclusive_minimum: typing.Optional[typing.Union[int, float, decimal.Decimal]] = None,
        exclusive_maximum: typing.Optional[typing.Union[int, float, decimal.Decimal]] = None,
        precision: typing.Optional[str] = None,
        multiple_of: typing.Optional[typing.Union[int, float, decimal.Decimal]] = None,
        coerce_types: bool = True,
        **kwargs: typing.Any,
    ) -> None:
        super().__init__(**kwargs)
        assert minimum is None or isinstance(minimum, (int, float, decimal.Decimal))
        assert maximum is None or isinstance(maximum, (int, float, decimal.Decimal))
        assert exclusive_minimum is None or isinstance(
            exclusive_minimum, (int, float, decimal.Decimal)
        )
        assert exclusive_maximum is None or isinstance(
            exclusive_maximum, (int, float, decimal.Decimal)
        )
        assert multiple_of is None or isinstance(multiple_of, (int, float, decimal.Decimal))

        self.minimum = minimum
        self.maximum = maximum
        self.exclusive_minimum = exclusive_minimum
        self.exclusive_maximum = exclusive_maximum
        self.precision = precision
        self.multiple_of = multiple_of
        self.coerce_types = coerce_types

    def check(self, value: typing.Any) -> typing.Any:
        if value is None and self.null:
            return None
        elif value == "" and self.null and self.coerce_types:
            return None
        elif value is None:
            raise self.validation_error("null")
        elif isinstance(value, bool):
            raise self.validation_error("type")
        elif self.field_type is int and isinstance(value, float) and not value.is_integer():
            raise self.validation_error("integer")
        elif not isinstance(value, (int, float)) and not self.coerce_types:
            raise self.validation_error("type")

        try:
            if isinstance(value, str):
                value = decimal.Decimal(value)
            if self.field_type is not None:
                value = self.field_type(value)
        except (TypeError, ValueError, decimal.InvalidOperation):
            raise self.validation_error("type")  # noqa

        if not isfinite(value):
            raise self.validation_error("finite")

        if self.precision is not None:
            field_type = self.field_type or type(value)
            quantize_val = decimal.Decimal(self.precision)
            decimal_val = decimal.Decimal(value)
            decimal_val = decimal_val.quantize(quantize_val, rounding=decimal.ROUND_HALF_UP)
            value = field_type(decimal_val)

        if self.minimum is not None and value < self.minimum:
            raise self.validation_error("minimum", self.minimum)

        if self.exclusive_minimum is not None and value <= self.exclusive_minimum:
            raise self.validation_error("exclusive_minimum", self.exclusive_minimum)

        if self.maximum is not None and value > self.maximum:
            raise self.validation_error("maximum", self.maximum)

        if self.exclusive_maximum is not None and value >= self.exclusive_maximum:
            raise self.validation_error("exclusive_maximum", self.exclusive_maximum)

        if self.multiple_of is not None:
            if isinstance(self.multiple_of, int):
                if value % self.multiple_of:
                    raise self.validation_error("multiple_of", self.multiple_of)
            else:
                if not (value * (1 / self.multiple_of)).is_integer():
                    raise self.validation_error("multiple_of", self.multiple_of)
        return value


class Integer(Number):
    field_type: typing.Any = int


class Float(Number):
    field_type: typing.Any = float


class Decimal(Number):
    field_type: typing.Any = decimal.Decimal


class Boolean(SaffierField):
    error_messages: typing.Dict[str, str] = {
        "type": "Must be a boolean.",
        "null": "May not be null.",
    }
    coerse_values: typing.Mapping[typing.Union[str, int], bool] = {
        "true": True,
        "false": False,
        "on": True,
        "off": False,
        "1": True,
        "0": False,
        "": False,
        1: True,
        0: False,
    }
    coerce_null_values: typing.Set[str] = {"", "null", "none"}

    def __init__(self, *, coerce_types: bool = True, **kwargs: typing.Any) -> None:
        super().__init__(**kwargs)
        self.coerce_types = coerce_types

    def check(self, value: typing.Any) -> typing.Any:
        if value is None and self.null:
            return None
        elif value is None:
            raise self.validation_error("null")
        elif not isinstance(value, bool):
            if not self.coerce_types:
                raise self.validation_error("type")
            if isinstance(value, str):
                value = value.lower()

            if self.null and value in self.coerce_null_values:
                return None
            try:
                value = self.coerse_values[value]
            except (KeyError, TypeError):
                raise self.validation_error("type")  # noqa
        return value


class Choice(SaffierField):
    error_messages: typing.Dict[str, str] = {
        "null": "May not be null.",
        "required": "This field is required.",
        "choice": "Not a valid choice.",
    }

    def __init__(
        self,
        *,
        choices: typing.Optional[
            typing.Sequence[typing.Union[str, typing.Tuple[str, str]]]
        ] = None,
        coerce_types: bool = True,
        **kwargs: typing.Any,
    ) -> None:
        super().__init__(**kwargs)
        self.choices = [
            (choice if isinstance(choice, (tuple, list)) else (choice, choice))
            for choice in choices or []
        ]
        self.coerce_types = coerce_types
        assert all(len(choice) == 2 for choice in self.choices)

    def check(self, value: typing.Any) -> typing.Any:
        if value is None and self.null:
            return None
        elif value is None:
            raise self.validation_error("null")
        elif value not in Uniqueness([key for key, value in self.choices]):
            if value == "":
                if self.null and self.coerce_types:
                    return None
                raise self.validation_error("required")
            raise self.validation_error("required")
        return value


class Text(String):
    def __init__(self, **kwargs: typing.Any) -> None:
        super().__init__(format="text", **kwargs)


class Date(String):
    def __init__(self, **kwargs: typing.Any) -> None:
        super().__init__(format="date", **kwargs)


class Time(String):
    def __init__(self, **kwargs: typing.Any) -> None:
        super().__init__(format="time", **kwargs)


class DateTime(String):
    def __init__(self, **kwargs: typing.Any) -> None:
        super().__init__(format="datetime", **kwargs)


class Union(SaffierField):
    error_messages: typing.Dict[str, str] = {
        "null": "May not be null.",
        "union": "Did not match any valid type.",
    }

    def __init__(self, any_of: typing.List[SaffierField], **kwargs: typing.Any):
        super().__init__(**kwargs)

        self.any_of = any_of
        if any(child.null for child in any_of):
            self.allow_null = True

    def check(self, value: typing.Any) -> typing.Any:
        if value is None and self.allow_null:
            return None
        elif value is None:
            raise self.validation_error("null")

        candidate_errors = []
        for child in self.any_of:
            validated, error = child.validate_or_error(value)
            if error is None:
                return validated
            else:
                # If a child returned anything other than a type error, then
                # it is a candidate for returning as the primary error.
                messages = error.messages()
                if len(messages) != 1 or messages[0].code != "type" or messages[0].index:
                    candidate_errors.append(error)

        if len(candidate_errors) == 1:
            # If exactly one child was of the correct type, then we can use
            # the error from the child.
            raise candidate_errors[0]
        raise self.validation_error("union")


class Any(SaffierField):
    def check(self, value: typing.Any) -> typing.Any:
        return value


class Const(SaffierField):
    """
    Only ever matches the given given value.
    """

    error_messages: typing.Dict[str, str] = {
        "only_null": "Must be null.",
        "const": "Must be the value '{const}'.",
    }

    def __init__(self, const: typing.Any, **kwargs: typing.Any):
        assert "null" not in kwargs
        super().__init__(**kwargs)
        self.const = const

    def check(self, value: typing.Any) -> typing.Any:
        if value != self.const:
            if self.const is None:
                raise self.validation_error("only_null")
            raise self.validation_error("const", self.const)
        return value


class UUID(String):
    def __init__(self, **kwargs: typing.Any) -> None:
        super().__init__(format="uuid", **kwargs)


class Email(String):
    def __init__(self, **kwargs: typing.Any) -> None:
        super().__init__(format="email", **kwargs)


class Password(String):
    def __init__(self, **kwargs: typing.Any) -> None:
        super().__init__(format="password", **kwargs)


class IPAddress(String):
    def __init__(self, **kwargs: typing.Any) -> None:
        super().__init__(format="ipaddress", **kwargs)


class URL(String):
    def __init__(self, **kwargs: typing.Any) -> None:
        super().__init__(format="url", **kwargs)
