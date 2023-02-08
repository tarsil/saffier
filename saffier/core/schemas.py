from typing import Any, Dict, Mapping, Type

from pydantic.fields import Undefined

from saffier.core.base import Message
from saffier.core.fields import SaffierField
from saffier.exceptions import ValidationError
from saffier.types import DictAny


class Schema(SaffierField):
    error_messages: Dict[str, str] = {
        "type": "Must be an object.",
        "null": "May not be null.",
        "invalid_key": "All object keys must be strings.",
        "required": "This field is required.",
    }

    def __init__(
        self, default: Any = Undefined, *, fields: Dict[str, Type[SaffierField]], **kwargs: DictAny
    ) -> Any:
        super().__init__(default=default, **kwargs)
        self.fields = fields
        self.required = [
            key for key, field in fields.items() if not (field.read_only or field.has_default())
        ]

    def validate(self, value: Any) -> Any:
        """
        General function used for validation of the generated schema.
        """
        if value is None and self.allow_null:
            return None
        elif value is None:
            raise self.validation_error("null")
        elif not isinstance(value, (dict, Mapping)):
            raise self.validation_error("type")

        validated = {}
        error_messages = []

        for key in value.keys():
            if not isinstance(key, str):
                text = self.get_error_message("invalid_key")
                message = Message(text=text, code="required", index=[key])
                error_messages.append(message)

        for key in self.required:
            if key not in value:
                text = self.get_error_message("required")
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
                error_messages += error.messages(prefix=key)

        if error_messages:
            raise ValidationError(messages=error_messages)
        return validated
