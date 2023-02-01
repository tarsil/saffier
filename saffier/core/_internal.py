import typing
from optparse import NO_DEFAULT
from re import L

from pydantic.fields import FieldInfo

from saffier.core.base import ValidationResult
from saffier.exceptions import ValidationError

NO_DEFAULT = object()


class SaffierField(FieldInfo):
    error_messages = typing.Dict[str, str] = {}

    def __init__(
        self,
        default: typing.Any = NO_DEFAULT,
        null: bool = False,
        read_only: bool = False,
        **kwargs: typing.Any
    ) -> None:
        if null and default is NO_DEFAULT:
            default = None

        if default is not NO_DEFAULT:
            self.default = default
        super().__init__(default, **kwargs)
        self.null = null
        self.read_only = read_only

    def validate(self, value: typing.Any) -> typing.Any:
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

    def has_default(self) -> bool:
        return hasattr(self, "default")

    def validate_or_error(self, value: typing.Any) -> ValidationResult:
        try:
            value = self.validate(value)
        except ValidationError as error:
            return ValidationResult(value=None, error=error)
        return ValidationResult(value=value, error=None)

    def validation_error(
        self, code: str, value: typing.Optional[typing.Any] = None
    ) -> ValidationError:
        text = self.get_error_message(code)
        if value:
            text = text.format(*value)
        return ValidationError(detail=text)

    def get_error_message(self, code: str) -> str:
        return self.errors[code].format(**self.__dict__)

    def get_default_value(self) -> typing.Any:
        default = getattr(self, "default", None)
        if callable(default):
            return default()
        return default

    def transform(self, obj: typing.Any) -> typing.Any:
        return obj
