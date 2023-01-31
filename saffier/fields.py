from datetime import date, datetime
from typing import Any, Optional, Tuple, Type, Union

import sqlalchemy
from django.db.models import CharField as DChar
from pydantic import validators
from typesystem import String

from saffier.pydantic import SaffierField
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
        **kwargs: DictAny,
    ) -> None:
        if primary_key:
            kwargs["read_only"] = True
        self.null = kwargs.pop("null", False)
        self.primary_key = primary_key
        self.index = index
        self.unique = unique
        self.validator: Union["SaffierField", Type["SaffierField"]] = self.get_validator(**kwargs)

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
            unique=self.unique,
        )

    def get_validator(self, **kwargs: DictAny) -> SaffierField:
        return SaffierField(**kwargs)  # pragma: no cover

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        raise NotImplemented()  # pragma: no cover

    def get_constraints(self):
        return []

    def expand_relationship(self, value):
        return value


class CharField(Field):
    """
    Representation a StringField text with a max_length.
    """

    def __init__(self, **kwargs: DictAny) -> None:
        assert "max_length" in kwargs, "max_length is required"
        super().__init__(**kwargs)

    def get_validator(self, **kwargs: DictAny) -> SaffierField:
        return SaffierField(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.String(length=self.validator.max_length)


class TextField(Field):
    """
    Representation of a TextField for a big length of text
    """

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.Text()


class IntegerField(Field):
    """
    Representation of an IntegerField
    """

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.Integer()


class FloatField(Field):
    """
    Representation of a Decimal floating field
    """

    def __init__(self, **kwargs: DictAny) -> None:
        assert "max_digits" in kwargs, "max_digits is required"
        assert "decimal_places" in kwargs, "decimal_places is required"
        super().__init__(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.Float(
            precision=self.validator.max_digits, decimal_return_scale=self.validator.decimal_places
        )


class BigIntegerField(Field):
    """
    Represents a BigIntegerField
    """

    def get_column_type(self):
        return sqlalchemy.BigInteger()


class BooleanField(Field):
    """
    Representation of a boolean
    """

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.Boolean()


class AutoNowMixin(Field):
    """
    Represents a date time with defaults for automatic now()
    """

    def __init__(self, auto_now=False, auto_now_add=False, **kwargs):
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add
        if auto_now_add and auto_now:
            raise ValueError("auto_now and auto_now_add cannot be both True")
        if auto_now_add or auto_now:
            kwargs["read_only"] = True
        super().__init__(**kwargs)


class DateTimeField(AutoNowMixin):
    """
    Representation of a datetime
    """

    def get_validator(self, **kwargs) -> SaffierField:
        if self.auto_now_add or self.auto_now:
            kwargs["default"] = datetime.now
        return SaffierField(**kwargs)

    def get_column_type(self):
        return sqlalchemy.DateTime()


class DateField(AutoNowMixin):
    """
    Representation of a Date
    """

    def get_validator(self, **kwargs) -> SaffierField:
        if self.auto_now_add or self.auto_now:
            kwargs["default"] = date.today
        return SaffierField(**kwargs)

    def get_column_type(self):
        return sqlalchemy.Date()


class TimeField(Field):
    """
    Representation of time
    """

    def get_column_type(self):
        return sqlalchemy.Time()


class JSONField(Field):
    """
    JSON Representation of an object field
    """

    def get_column_type(self):
        return sqlalchemy.JSON()


class ForeignKey(Field):
    """
    ForeignKey field object
    """

    class ForeignKeyValidator(SaffierField):
        def validate(self, value: Any) -> Any:
            return value.pk

    def __init__(self, to: Any, null: bool = False, on_delete: Optional[str] = None):
        super().__init__(null=null)
        self.to = to
        self.on_delete = on_delete

    @property
    def target(self):
        if hasattr(self, "_target"):
            if isinstance(self.to, str):
                self._target = self.registry_models[self.to]
            else:
                self._target = self.to
        return self._target

    def get_validator(self, **kwargs: DictAny) -> SaffierField:
        return self.ForeignKeyValidator(**kwargs)

    def get_column(self, name: str) -> sqlalchemy.Column:
        target = self.target
        to_field = target.fields[target.pkname]

        column_type = to_field.get_column_type()
        constraints = [
            sqlalchemy.schema.ForeignKey(
                f"{target.tablename}.{target.pkname}", ondelete=self.on_delete
            )
        ]
        return sqlalchemy.Column(name, column_type, *constraints, nullable=self.null)

    def expand_relationship(self, value):
        target = self.target
        if isinstance(value, target):
            return value
        return target(pk=value)


class OneToOneField(ForeignKey):
    """
    Representation of a one to one field.
    """

    def get_column(self, name: str) -> sqlalchemy.Column:
        target = self.target
        to_field = target.fields[target.pkname]

        column_type = to_field.get_column_type()
        constraints = [
            sqlalchemy.schema.ForeignKey(
                f"{target.tablename}.{target.pkname}", ondelete=self.on_delete
            )
        ]
        return sqlalchemy.Column(
            name,
            column_type,
            *constraints,
            nullable=self.null,
            unique=True,
        )
