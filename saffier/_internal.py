from typing import Any

from pydantic import Field


class SaffierField(Field):
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


class AnyField(Field):
    """
    Always matches.
    """

    def validate(self, value: Any) -> Any:
        return value
