from typing import TYPE_CHECKING, Any, Dict, Mapping, Type

from pydantic import ValidationError
from pydantic.fields import Undefined

from saffier.core.base import Message
from saffier.core.datastructures import ArbitraryHashableBaseModel
from saffier.types import DictAny

if TYPE_CHECKING:
    from saffier.core._internal import SaffierField

NO_DEFAULT = object()


class Schema(ArbitraryHashableBaseModel):
    """
    The base model for the schemas
    """

    validation_errors: Dict[str, str] = {
        "type": "Must be an object.",
        "null": "May not be null.",
        "invalid_key": "All object keys must be strings.",
        "required": "This field is required.",
    }

    def __init__(
        self,
        default: Any = Undefined,
        *,
        fields: Dict[str, Type["SaffierField"]],
        **kwargs: DictAny
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
