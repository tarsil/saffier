import typing

from pydantic import root_validator
from pydantic.dataclasses import dataclass

from saffier.core.datastructures import ArbitraryHashableBaseModel
from saffier.types import DictAny


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
    def validate_data(cls, values):
        name = values.get("name")

        if len(name) > cls.max_name_length:
            raise ValueError(f"The max length of the index name must be 30. Got {len(name)}")

        fields = values.get("fields")
        if not isinstance(fields, (tuple, list)):
            raise ValueError("Index.fields must be a list or a tuple.")

        if fields and not all(isinstance(field, str) for field in fields):
            raise ValueError("Index.fields must contain only strings with field names.")