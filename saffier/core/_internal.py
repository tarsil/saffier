from optparse import NO_DEFAULT
from typing import Any, Dict, Mapping, Union

from pydantic import BaseConfig, ValidationError
from pydantic.fields import FieldInfo, Undefined

from saffier.core.base import Message, ValidationResult
from saffier.types import DictAny

NO_DEFAULT = object()


class SaffierField(FieldInfo):
    error_messages = Dict[str, str] = {}

    def __init__(
        self, default: Any = NO_DEFAULT, null: bool = False, read_only: bool = False, **kwargs: Any
    ) -> None:
        if null and default is NO_DEFAULT:
            default = None

        if default is not NO_DEFAULT:
            self.default = default
        super().__init__(default, **kwargs)
        self.null = null
        self.read_only = read_only

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

    def has_default(self) -> bool:
        return hasattr(self, "default")

    def validate_or_error(self, value: Any) -> ValidationResult:
        try:
            value = self.validate(value)
        except ValidationError as error:
            return ValidationResult(value=None, error=error)
        return ValidationResult(value=value, error=None)

    def get_default_value(self) -> Any:
        default = getattr(self, "default", None)
        if callable(default):
            return default()
        return default

    def __or__(self, other: "SaffierField") -> "Union":
        if isinstance(self, Union):
            any_of = self.any_of
        else:
            any_of = [self]

        if isinstance(other, Union):
            any_of += other.any_of
        else:
            any_of += [other]

        return Union(any_of=any_of)


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

    validation_errors = {
        "type": "Must be an object.",
        "null": "May not be null.",
        "invalid_key": "All object keys must be strings.",
        "required": "This field is required.",
    }

    def __init__(
        self, default: Any = Undefined, *, fields: Dict[str, SaffierField], **kwargs: DictAny
    ) -> Any:
        kwargs.update(fields=fields)
        super().__init__(default=default, **kwargs)
        self.fields = fields

    def validate(self, value: Any) -> Any:
        """
        General function used for validation of the generated schema.
        """
        if value is None and self.allow_null:
            return None
        elif value is None:
            raise ValueError(self.validation_errors["null"])
        elif not isinstance(value, (dict, Mapping)):
            raise ValueError(self.validation_errors["type"])

        validated = {}
        error_messages = []

        # Making sure all the keys are strings
        for key in value.keys():
            if not isinstance(key, str):
                text = self.validation_errors["invalid_key"]
                message = Message(text=text, code="required", index=[key])
                error_messages.append(message)

        for key, child_schema in self.fields.items():
            if child_schema.read_only:
                continue

            if key not in value:
                if child_schema.has_default():
                    validated[key] = child_schema.get_default_value()
                continue

            item = value[key]
            child_value, error = child_schema.validate_or_error(item)
            if not error:
                validated[key] = child_value
            else:
                error_messages += error.messages(add_prefix=key)

        if error_messages:
            raise ValidationError(errors=error_messages)
        return validated

    class Config(BaseConfig):
        extra = "allow"
        arbitrary_types_allowed = True
