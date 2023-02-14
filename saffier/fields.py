import typing
from datetime import date, datetime

import sqlalchemy

from saffier.db.fields import (
    URL,
    UUID,
    Any,
    Boolean,
    Date,
    DateTime,
    Decimal,
    Email,
    Float,
    Integer,
)
from saffier.db.fields import IPAddress as CoreIPAddress
from saffier.db.fields import SaffierField, String, Time
from saffier.sqlalchemy.fields import GUID, IPAddress, List
from saffier.types import DictAny


class Field:
    """
    Base field for the model declaration fields.
    """

    def __init__(
        self,
        *,
        primary_key: bool = False,
        index: bool = False,
        unique: bool = False,
        **kwargs: DictAny,
    ) -> None:
        if primary_key:
            kwargs["read_only"] = True
        self.null = kwargs.get("null", False)
        self.primary_key = primary_key
        self.index = index
        self.unique = unique
        self.validator: typing.Union[SaffierField, typing.Type[SaffierField]] = self.get_validator(
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
        return String(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.String(length=self.validator.max_length)


class TextField(Field):
    """
    Representation of a TextField for a big length of text
    """

    def get_validator(self, **kwargs: DictAny) -> SaffierField:
        return String(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.Text()


class IntegerField(Field):
    """
    Representation of an IntegerField
    """

    def get_validator(self, **kwargs: DictAny) -> SaffierField:
        return Integer(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.Integer()


class FloatField(Field):
    """
    Representation of a Decimal floating field
    """

    def __init__(self, **kwargs: DictAny) -> None:
        super().__init__(**kwargs)

    def get_validator(self, **kwargs: DictAny) -> SaffierField:
        return Float(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.Float()


class BigIntegerField(Field):
    """
    Represents a BigIntegerField
    """

    def get_validator(self, **kwargs: DictAny) -> SaffierField:
        return Integer(**kwargs)

    def get_column_type(self):
        return sqlalchemy.BigInteger()


class BooleanField(Field):
    """
    Representation of a boolean
    """

    def get_validator(self, **kwargs: DictAny) -> SaffierField:
        return Boolean(**kwargs)

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
        return DateTime(**kwargs)

    def get_column_type(self):
        return sqlalchemy.DateTime()


class DateField(AutoNowMixin):
    """
    Representation of a Date
    """

    def get_validator(self, **kwargs) -> SaffierField:
        if self.auto_now_add or self.auto_now:
            kwargs["default"] = date.today
        return Date(**kwargs)

    def get_column_type(self):
        return sqlalchemy.Date()


class TimeField(Field):
    """
    Representation of time
    """

    def get_validator(self, **kwargs: DictAny) -> SaffierField:
        return Time(**kwargs)

    def get_column_type(self):
        return sqlalchemy.Time()


class JSONField(Field):
    """
    JSON Representation of an object field
    """

    def get_validator(self, **kwargs: DictAny) -> SaffierField:
        return Any(**kwargs)

    def get_column_type(self):
        return sqlalchemy.JSON()


class ForeignKey(Field):
    """
    ForeignKey field object
    """

    class ForeignKeyValidator(SaffierField):
        def validate(self, value: typing.Any) -> typing.Any:
            return value.pk

    def __init__(self, to: typing.Any, null: bool = False, on_delete: typing.Optional[str] = None):
        super().__init__(null=null)
        self.to = to
        self.on_delete = on_delete

    @property
    def target(self):
        if not hasattr(self, "_target"):
            if isinstance(self.to, str):
                self._target = self.registry.models[self.to]
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
                f"{target._meta.tablename}.{target.pkname}", ondelete=self.on_delete
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
                f"{target._meta.tablename}.{target.pkname}", ondelete=self.on_delete
            )
        ]
        return sqlalchemy.Column(
            name,
            column_type,
            *constraints,
            nullable=self.null,
            unique=True,
        )


class ChoiceField(Field):
    """
    Representation of an Enum
    """

    def __init__(
        self,
        choices: typing.Sequence[typing.Union[typing.Tuple[str, str], typing.Tuple[str, int]]],
        **kwargs: DictAny,
    ) -> None:
        super().__init__(**kwargs)
        self.choices = choices

    def get_validator(self, **kwargs: DictAny) -> Any:
        return Any(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.Enum(self.choices)


class DecimalField(Field):
    """
    Representation of a DecimalField
    """

    def __init__(self, max_digits: int, decimal_places: int, **kwargs):
        assert max_digits, "max_digits is required"
        assert decimal_places, "decimal_places is required"
        self.max_digits = max_digits
        self.decimal_places = decimal_places
        super().__init__(**kwargs)

    def get_validator(self, **kwargs: DictAny) -> SaffierField:
        return Decimal(**kwargs)

    def get_column_type(self):
        return sqlalchemy.Numeric(precision=self.max_digits, scale=self.decimal_places)


class UUIDField(Field):
    """
    Representation of UUID
    """

    def get_validator(self, **kwargs: DictAny) -> SaffierField:
        return UUID(**kwargs)

    def get_column_type(self):
        return GUID()


class IPAddressField(Field):
    """
    Representation of UUUID
    """

    def get_validator(self, **kwargs: DictAny) -> SaffierField:
        return CoreIPAddress(**kwargs)

    def get_column_type(self):
        return IPAddress()


class EmailField(CharField):
    def get_validator(self, **kwargs) -> SaffierField:
        return Email(**kwargs)

    def get_column_type(self):
        return sqlalchemy.String(length=self.validator.max_length)


class URLField(CharField):
    def get_validator(self, **kwargs) -> SaffierField:
        return URL(**kwargs)

    def get_column_type(self):
        return sqlalchemy.String(length=self.validator.max_length)


class ListField(Field):
    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return List()
