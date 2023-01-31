from datetime import date, datetime
from typing import Any, Optional, Tuple, Type, Union

import sqlalchemy
from django.db.models import CharField as DChar
from pydantic import Field as PydanticField

from saffier.sqlalchemy.fields import GUIDField, IPField, ListField
from saffier.types import DictAny


class Field:
    """
    Base field for the model declaration fields.
    """

    def __init__(
        self,
        primary_key: bool = False,
        index: bool = False,
        unique: bool = False,
        **kwargs: DictAny
    ) -> None:
        if primary_key:
            kwargs["read_only"] = True
        self.null = kwargs.pop("null", False)
        self.primary_key = primary_key
        self.index = index
        self.unique = unique
        self.validator: Union["PydanticField", Type["PydanticField"]] = self.get_validator(
            **kwargs
        )

    def get_column(self, name: str) -> sqlalchemy.Column:
        """
        Returns a column type for the model field.
        """
        column_type = self.get_column_type()
        constraints = self.get_constraints()
        return sqlalchemy.Column(
            name,
            column_type,
            *constraints,
            primary_key=self.primary_key,
            nullable=self.null and not self.primary_key,
            index=self.index,
            unique=self.unique
        )

    def get_validator(self, **kwargs: DictAny) -> PydanticField:
        raise NotImplemented()  # pragma: no cover

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        raise NotImplemented()  # pragma: no cover

    def get_constraints(self):
        return []

    def expand_relationship(self, value):
        return value


class CharField(Field):
    """
    Represents a string text frmo the base Field.
    """

    def __init__(self, **kwargs: DictAny) -> None:
        assert "max_length" in kwargs, "max_length is required"
        super().__init__(**kwargs)

    def get_validator(self, **kwargs: DictAny) -> PydanticField:
        return PydanticField(default=str, **kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.String(length=self.validator.max_length)
