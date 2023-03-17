import typing

from pydantic import root_validator
from pydantic.dataclasses import dataclass


@dataclass
class Index:
    """
    Class responsible for handling and declaring the database indexes.
    """

    suffix: str = "idx"
    max_name_length: int = 30
    name: typing.Optional[str] = None
    fields: typing.Optional[typing.List[str]] = None

    @root_validator
    def validate_data(cls, values) -> typing.Any:  # type: ignore
        name = values.get("name")

        if name is not None and len(name) > cls.max_name_length:
            raise ValueError(f"The max length of the index name must be 30. Got {len(name)}")

        fields = values.get("fields")
        if not isinstance(fields, (tuple, list)):
            raise ValueError("Index.fields must be a list or a tuple.")

        if fields and not all(isinstance(field, str) for field in fields):
            raise ValueError("Index.fields must contain only strings with field names.")

        if name is None:
            suffix = values.get("suffix", cls.suffix)
            values["name"] = f"{'_'.join(fields)}_{suffix}"

        return values


@dataclass
class UniqueConstraint:
    """
    Class responsible for handling and declaring the database unique_together.
    """

    fields: typing.List[str]

    @root_validator
    def validate_data(cls, values) -> typing.Any:  # type: ignore
        fields = values.get("fields")
        if not isinstance(fields, (tuple, list)):
            raise ValueError("UniqueConstraint.fields must be a list or a tuple.")

        if fields and not all(isinstance(field, str) for field in fields):
            raise ValueError("UniqueConstraint.fields must contain only strings with field names.")

        return values
