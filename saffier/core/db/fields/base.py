"""Concrete field classes used when declaring Saffier models."""

import copy
import decimal
import enum
import typing
from datetime import date, datetime, timedelta

import sqlalchemy
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.mutable import MutableList

import saffier
from saffier.conf import settings
from saffier.contrib.sqlalchemy.fields import IPAddress
from saffier.core.db.constants import CASCADE, NEW_M2M_NAMING, RESTRICT, SET_NULL
from saffier.core.db.context_vars import CURRENT_INSTANCE, EXPLICIT_SPECIFIED_VALUES
from saffier.core.db.fields._internal import (
    URL,
    UUID,
    Any,
    Binary,
    Boolean,
    Date,
    DateTime,
    Decimal,
    Duration,
    Email,
    Float,
    Integer,
    Password,
    SaffierField,
    String,
    Time,
)
from saffier.core.db.fields._internal import IPAddress as CoreIPAddress
from saffier.core.terminal import Print
from saffier.exceptions import FieldDefinitionError, ImproperlyConfigured, ModelReferenceError

if typing.TYPE_CHECKING:
    from saffier import Model

terminal = Print()
CHAR_LIMIT = 63


class Field:
    """Base class for Saffier model fields.

    A field coordinates three layers of behavior: runtime validation through an
    internal validator, SQLAlchemy column generation, and ORM-specific input or
    relation normalization. Concrete subclasses usually override at least the
    validator or the column type, while relation-aware fields also override
    input normalization and pre-save behavior.
    """

    is_virtual: bool = False

    def __init__(
        self,
        *,
        primary_key: bool = False,
        index: bool = False,
        unique: bool = False,
        **kwargs: typing.Any,
    ) -> None:
        self.server_default = kwargs.pop("server_default", None)
        if primary_key:
            default_value = kwargs.get("default")
            self.raise_for_non_default(default=default_value, server_default=self.server_default)
            kwargs["read_only"] = True

        self.null = kwargs.get("null", False)
        self.default_value = kwargs.get("default")
        self.primary_key = primary_key
        self.index = index
        self.unique = unique
        self.validator: SaffierField | type[SaffierField] = self.get_validator(**kwargs)
        self.comment = kwargs.get("comment")
        self.column_name = kwargs.pop("column_name", None)
        self.owner = kwargs.pop("owner", None)
        self.registry = kwargs.pop("registry", None)
        self.name = kwargs.pop("name", "")
        self.inherit = kwargs.pop("inherit", True)
        self.no_copy = kwargs.pop("no_copy", False)
        self.exclude = kwargs.pop("exclude", False)
        self.inject_default_on_partial_update = kwargs.get(
            "inject_default_on_partial_update",
            False,
        )
        self.server_onupdate = kwargs.pop("server_onupdate", None)
        self.autoincrement = kwargs.pop("autoincrement", False)
        self.secret = kwargs.pop("secret", False)

    def get_column(self, name: str) -> sqlalchemy.Column:
        """Build the SQLAlchemy column used to persist this field.

        Args:
            name: Logical field name declared on the model.

        Returns:
            sqlalchemy.Column: SQLAlchemy column configured from the field
            options and validator metadata.
        """
        column_type = self.get_column_type()
        constraints = self.get_constraints()
        column_kwargs = {
            "primary_key": self.primary_key,
            "nullable": self.null and not self.primary_key,
            "index": self.index,
            "unique": self.unique,
            "default": self.default_value,
            "comment": self.comment,
            "server_default": self.server_default,
        }
        if self.autoincrement:
            column_kwargs["autoincrement"] = True

        return sqlalchemy.Column(
            self.column_name or name,
            column_type,
            *constraints,
            key=name,
            **column_kwargs,
        )

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return SaffierField(**kwargs)  # pragma: no cover

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        raise NotImplementedError()  # pragma: no cover

    def get_constraints(self) -> typing.Any:
        return []

    def get_columns(self, name: str) -> typing.Sequence[sqlalchemy.Column]:
        return [self.get_column(name)]

    def get_global_constraints(
        self,
        name: str,
        columns: typing.Sequence[sqlalchemy.Column],
        *,
        schema: str | None = None,
    ) -> typing.Sequence[sqlalchemy.Constraint | sqlalchemy.Index]:
        del name, columns, schema
        return []

    def has_column(self) -> bool:
        return not self.is_virtual

    def get_embedded_fields(
        self,
        field_name: str,
        existing_fields: dict[str, "Field"],
    ) -> dict[str, "Field"]:
        del field_name, existing_fields
        return {}

    def expand_relationship(self, value: typing.Any) -> typing.Any:
        return value

    def clean(
        self, name: str, value: typing.Any, *, for_query: bool = False
    ) -> dict[str, typing.Any]:
        """Normalize one logical field value into column-value pairs.

        Args:
            name: Logical field name.
            value: User-facing field value.
            for_query: Reserved for field implementations that need distinct
                query-time normalization.

        Returns:
            dict[str, Any]: Database payload keyed by column name.
        """
        del for_query
        if not self.has_column():
            return {}
        return {name: value}

    def modify_input(self, name: str, kwargs: dict[str, typing.Any]) -> None:
        del name, kwargs

    def raise_for_non_default(self, default: typing.Any, server_default: typing.Any) -> typing.Any:
        del default, server_default

    def get_default_value(self) -> typing.Any:
        return self.validator.get_default_value()

    def has_default(self) -> bool:
        return self.validator.has_default()

    def get_default_values(
        self,
        field_name: str,
        cleaned_data: dict[str, typing.Any],
    ) -> dict[str, typing.Any]:
        if field_name in cleaned_data or not self.has_column():
            return {}
        return {field_name: self.get_default_value()}

    def is_required(self) -> bool:
        if self.primary_key and self.autoincrement:
            return False
        return not (self.null or self.server_default is not None or self.has_default())

    def get_is_null_clause(self, column: typing.Any) -> typing.Any:
        return column == None  # noqa: E711

    def get_is_empty_clause(self, column: typing.Any) -> typing.Any:
        return self.get_is_null_clause(column)

    def operator_to_clause(
        self,
        field_name: str,
        operator: str,
        table: sqlalchemy.Table,
        value: typing.Any,
    ) -> typing.Any:
        """Translate one lookup operator into a SQLAlchemy clause.

        Args:
            field_name: Logical field name being filtered.
            operator: Saffier lookup suffix such as `exact` or `isnull`.
            table: SQLAlchemy table containing the target column.
            value: Lookup value supplied by the caller.

        Returns:
            Any: SQLAlchemy boolean clause implementing the lookup.
        """
        column = table.columns[field_name]
        mapped_operator = settings.filter_operators.get(operator, operator)

        if mapped_operator == "isnull":
            is_null = self.get_is_null_clause(column)
            return is_null if value else sqlalchemy.not_(is_null)

        if mapped_operator == "isempty":
            is_empty = self.get_is_empty_clause(column)
            return is_empty if value else sqlalchemy.not_(is_empty)

        return getattr(column, mapped_operator)(value)


class CharField(Field):
    """Variable-length string field with an explicit maximum length.

    This is the standard field for bounded text columns and uses the string
    validator's `max_length` setting to size the SQL column.
    """

    def __init__(self, **kwargs: typing.Any) -> None:
        assert "max_length" in kwargs, "max_length is required"
        super().__init__(**kwargs)

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return String(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.String(length=self.validator.max_length)  # type: ignore

    def get_is_empty_clause(self, column: typing.Any) -> typing.Any:
        return sqlalchemy.or_(self.get_is_null_clause(column), column == "")


class TextField(Field):
    """Unbounded text field backed by a SQL `TEXT` column.

    Use this for large text payloads where a database-level length limit is not
    required.
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return String(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.Text()


class IntegerField(Field):
    """Integer field with optional auto-increment-on-save behavior.

    Besides standard integer storage, the field can increment itself during save
    operations, which is useful for counters and lightweight sequence fields.
    """

    def __init__(self, increment_on_save: int = 0, **kwargs: typing.Any) -> None:
        self.increment_on_save = increment_on_save
        if self.increment_on_save != 0:
            if kwargs.get("autoincrement"):
                raise FieldDefinitionError(
                    "'autoincrement' is incompatible with 'increment_on_save'"
                )
            if kwargs.get("null"):
                raise FieldDefinitionError("'null' is incompatible with 'increment_on_save'")
            kwargs.setdefault("read_only", True)
        super().__init__(**kwargs)

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Integer(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.Integer()

    def get_is_empty_clause(self, column: typing.Any) -> typing.Any:
        return sqlalchemy.or_(self.get_is_null_clause(column), column == 0)

    async def pre_save_callback(
        self,
        value: typing.Any,
        original_value: typing.Any,
        is_update: bool,
    ) -> dict[str, typing.Any]:
        if self.increment_on_save == 0:
            return {}

        explicit_values = EXPLICIT_SPECIFIED_VALUES.get()
        if explicit_values is not None and self.name in explicit_values:
            return {}

        current_value = original_value if value is None else value
        if not is_update:
            if current_value is None:
                return {self.name: self.get_default_value()}
            return {self.name: current_value + self.increment_on_save}

        if self.primary_key:
            return {}

        current_instance = CURRENT_INSTANCE.get()
        table = getattr(current_instance, "table", None)
        if table is None:
            if current_value is None:
                current_value = self.get_default_value()
            return {self.name: current_value + self.increment_on_save}
        return {self.name: table.columns[self.name] + self.increment_on_save}


class SmallIntegerField(IntegerField):
    """Integer field stored using the database's small-integer type.

    Use this when database-level storage size matters and the value range fits a
    small integer.
    """

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.SmallInteger()


class FloatField(Field):
    """Floating-point numeric field backed by a SQL `FLOAT` column.

    This field is appropriate for approximate numeric values where binary
    floating-point precision is acceptable.
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Float(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.Float()

    def get_is_empty_clause(self, column: typing.Any) -> typing.Any:
        return sqlalchemy.or_(self.get_is_null_clause(column), column == 0.0)


class BigIntegerField(Field):
    """Integer field stored using the database's big-integer type.

    Use this for identifiers or counters that may exceed standard integer
    ranges.
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Integer(**kwargs)

    def get_column_type(self) -> typing.Any:
        return sqlalchemy.BigInteger()


class BooleanField(Field):
    """Boolean field backed by a SQL `BOOLEAN` column.

    The field also supports `isempty` lookups by treating `False` as the empty
    value.
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Boolean(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.Boolean()

    def get_is_empty_clause(self, column: typing.Any) -> typing.Any:
        return sqlalchemy.or_(self.get_is_null_clause(column), column.is_(False))


class AutoNowMixin(Field):
    """Mixin for date/time fields that auto-populate themselves.

    `auto_now` refreshes the value on every save, while `auto_now_add` sets it
    only when the row is first created.
    """

    def __init__(
        self, auto_now: bool = False, auto_now_add: bool = False, **kwargs: typing.Any
    ) -> None:
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add
        if auto_now_add and auto_now:
            raise ValueError("auto_now and auto_now_add cannot be both True")
        if auto_now_add or auto_now:
            kwargs["read_only"] = True
        super().__init__(**kwargs)


class DateTimeField(AutoNowMixin):
    """Date-time field with optional automatic timestamping.

    It is commonly used for created-at and updated-at columns.
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        if self.auto_now_add or self.auto_now:
            kwargs["default"] = datetime.now
        return DateTime(**kwargs)

    def get_column_type(self) -> sqlalchemy.DateTime:
        return sqlalchemy.DateTime()


class DateField(AutoNowMixin):
    """Date-only field with optional automatic timestamping.

    It stores calendar dates without a time component.
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        if self.auto_now_add or self.auto_now:
            kwargs["default"] = date.today
        return Date(**kwargs)

    def get_column_type(self) -> sqlalchemy.Date:
        return sqlalchemy.Date()


class TimeField(Field):
    """Time-only field backed by a SQL `TIME` column.

    The field stores wall-clock time values without any date component.
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Time(**kwargs)

    def get_column_type(self) -> sqlalchemy.Time:
        return sqlalchemy.Time()


class DurationField(Field):
    """Timedelta field stored as a SQL interval/duration type.

    It accepts Python `timedelta` objects and can be queried for empty values by
    comparing against zero duration.
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Duration(**kwargs)

    def get_column_type(self) -> sqlalchemy.Interval:
        return sqlalchemy.Interval()

    def get_is_empty_clause(self, column: typing.Any) -> typing.Any:
        return sqlalchemy.or_(self.get_is_null_clause(column), column == timedelta())


class JSONField(Field):
    """JSON field for arbitrary structured payloads.

    The field treats JSON `null` as empty for `isnull` and `isempty` lookups so
    query behavior remains intuitive across databases.
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Any(**kwargs)

    def get_column_type(self) -> sqlalchemy.JSON:
        return sqlalchemy.JSON()

    def get_is_null_clause(self, column: typing.Any) -> typing.Any:
        casted = sqlalchemy.cast(column, sqlalchemy.Text())
        return sqlalchemy.or_(column.is_(sqlalchemy.null()), casted == "null")

    def get_is_empty_clause(self, column: typing.Any) -> typing.Any:
        casted = sqlalchemy.cast(column, sqlalchemy.Text())
        return sqlalchemy.or_(
            column.is_(sqlalchemy.null()),
            casted.in_(["null", "[]", "{}", "0", "0.0", '""']),
        )


class CompositeField(Field):
    """Virtual field that groups multiple model fields under one logical attribute.

    Composite fields let a model present several persisted columns as a single
    higher-level value object. They can wrap existing fields by name, inject new
    embedded fields inline, or instantiate a helper model/class when reading the
    value back from an instance.
    """

    is_virtual: bool = True

    def __init__(
        self,
        *,
        inner_fields: typing.Any = (),
        prefix_embedded: str = "",
        prefix_column_name: str = "",
        absorb_existing_fields: bool = False,
        model: typing.Any = None,
        **kwargs: typing.Any,
    ) -> None:
        kwargs.setdefault("null", True)
        super().__init__(**kwargs)
        self.inner_fields = inner_fields
        self.prefix_embedded = prefix_embedded
        self.prefix_column_name = prefix_column_name
        self.absorb_existing_fields = absorb_existing_fields
        self.model = model

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Any(**kwargs)

    def get_column(self, name: str) -> sqlalchemy.Column:
        raise RuntimeError(f"Virtual field '{name}' does not map to a database column.")

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        raise RuntimeError("CompositeField does not expose a column type.")

    def _iter_inner_items(
        self,
        existing_fields: dict[str, Field],
    ) -> list[tuple[str, Field] | str]:
        inner = self.inner_fields
        if hasattr(inner, "meta"):
            inner = typing.cast("dict[str, Field]", inner.meta.fields)
        if isinstance(inner, dict):
            inner = list(inner.items())

        collected: list[tuple[str, Field] | str] = []
        for item in inner:
            if isinstance(item, str) or (
                isinstance(item, tuple)
                and len(item) == 2
                and isinstance(item[0], str)
                and isinstance(item[1], Field)
            ):
                collected.append(item)
            elif isinstance(item, tuple) and len(item) == 1 and isinstance(item[0], str):
                collected.append(item[0])

        del existing_fields
        return collected

    def _field_target_name(self, public_name: str) -> str:
        if self.prefix_embedded:
            return f"{self.prefix_embedded}{public_name}"
        return public_name

    def get_embedded_fields(
        self,
        field_name: str,
        existing_fields: dict[str, Field],
    ) -> dict[str, Field]:
        del field_name
        embedded: dict[str, Field] = {}
        for item in self._iter_inner_items(existing_fields):
            if isinstance(item, str):
                continue
            public_name, inner_field = item
            if public_name == "pk":
                raise ValueError("sub field uses reserved name pk")
            if not getattr(inner_field, "inherit", True):
                continue

            target_name = self._field_target_name(public_name)
            if target_name in existing_fields and not self.absorb_existing_fields:
                continue

            field_copy = (
                inner_field if getattr(inner_field, "no_copy", False) else copy.copy(inner_field)
            )
            field_copy.name = target_name
            base_column_name = getattr(inner_field, "column_name", None) or public_name
            if self.prefix_column_name:
                field_copy.column_name = f"{self.prefix_column_name}{base_column_name}"
            embedded[target_name] = field_copy
        return embedded

    def _mapping(self, instance: typing.Any) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for item in self._iter_inner_items(instance.fields):
            if isinstance(item, str):
                target_name = self._field_target_name(item)
                if target_name in instance.fields:
                    mapping[item] = target_name
                elif item in instance.fields:
                    mapping[item] = item
                continue
            public_name, _ = item
            target_name = self._field_target_name(public_name)
            if target_name in instance.fields:
                mapping[public_name] = target_name
            elif public_name in instance.fields:
                mapping[public_name] = public_name
        return mapping

    def get_value(self, instance: typing.Any, field_name: str) -> typing.Any:
        del field_name
        values: dict[str, typing.Any] = {}
        for public_name, target_name in self._mapping(instance).items():
            values[public_name] = getattr(instance, target_name, None)
        if self.model is not None:
            try:
                return self.model(**values)
            except Exception:
                pass
        return values

    def set_value(self, instance: typing.Any, field_name: str, value: typing.Any) -> None:
        del field_name
        if value is None:
            return
        payload = value
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump()
        elif not isinstance(payload, dict):
            payload = {
                name: getattr(value, name) for name in dir(value) if not name.startswith("_")
            }
        for public_name, target_name in self._mapping(instance).items():
            if public_name in payload:
                setattr(instance, target_name, payload[public_name])

    def modify_input(self, name: str, kwargs: dict[str, typing.Any]) -> None:
        if name not in kwargs:
            return
        payload = kwargs.pop(name)
        if payload is None:
            return
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump()
        elif not isinstance(payload, dict):
            payload = {
                attr_name: getattr(payload, attr_name)
                for attr_name in dir(payload)
                if not attr_name.startswith("_")
            }

        owner = getattr(self, "owner", None)
        if owner is None:
            return

        for public_name, target_name in self._mapping(owner).items():
            if public_name in payload:
                kwargs[target_name] = payload[public_name]


class ForeignKey(Field):
    """Field that stores a relation to another Saffier model.

    Foreign keys in Saffier are capable of targeting simple or composite
    primary keys, deferred string references, cross-registry relations, and
    relation-aware deletion behavior. The field can therefore expand one
    logical attribute into multiple database columns and optionally manage the
    lifecycle of nested related objects during save operations.
    """

    class ForeignKeyValidator(SaffierField):
        def check(self, value: typing.Any) -> typing.Any:
            if value is None and self.null:
                return None
            if value is None:
                raise self.validation_error("null")
            if hasattr(value, "pk"):
                return value.pk
            return value

    def __init__(
        self,
        to: type["Model"] | str,
        null: bool = False,
        on_delete: str = RESTRICT,
        on_update: str = CASCADE,
        related_name: str | None = None,
        embed_parent: tuple[str, str] | None = None,
        no_constraint: bool = False,
        remove_referenced: bool = False,
        use_model_based_deletion: bool = False,
        force_cascade_deletion_relation: bool = False,
        **kwargs: Any,
    ):
        if on_delete is None:
            raise FieldDefinitionError("on_delete must not be null.")

        if on_delete == SET_NULL and not null:
            raise FieldDefinitionError("When SET_NULL is enabled, null must be True.")

        if on_update and (on_update == SET_NULL and not null):
            raise FieldDefinitionError("When SET_NULL is enabled, null must be True.")

        primary_key = bool(kwargs.pop("primary_key", False))
        index = bool(kwargs.pop("index", False))
        unique = bool(kwargs.pop("unique", False))
        self.related_fields = tuple(kwargs.pop("related_fields", ()))
        self._target_registry = kwargs.pop("target_registry", None)
        super().__init__(
            null=null,
            primary_key=primary_key,
            index=index,
            unique=unique,
            **kwargs,
        )
        self.to = to
        self.on_delete = on_delete
        self.on_update = on_update or CASCADE
        self.related_name = related_name
        self.embed_parent = embed_parent
        self.no_constraint = no_constraint
        self.remove_referenced = remove_referenced
        self.use_model_based_deletion = use_model_based_deletion
        self.force_cascade_deletion_relation = force_cascade_deletion_relation

        if embed_parent and "__" in embed_parent[1]:
            raise FieldDefinitionError(
                '"embed_parent" second argument (for embedding parent) cannot contain "__".'
            )

    @property
    def target_registry(self) -> typing.Any:
        """Return the registry used to resolve string relation targets.

        Explicit `target_registry` overrides take precedence, followed by the
        owning model registry and finally the field-level registry fallback.
        """
        if self._target_registry is not None:
            return self._target_registry
        owner_registry = getattr(getattr(self.owner, "meta", None), "registry", None)
        if owner_registry is not None:
            return owner_registry
        return self.registry

    @target_registry.setter
    def target_registry(self, value: typing.Any) -> None:
        self._target_registry = value

    @property
    def target(self) -> typing.Any:
        """Resolve and cache the target model class for this relation.

        String targets are looked up lazily so models can reference classes that
        are declared later in the import graph.

        Returns:
            Any: Resolved target model class.
        """
        if not hasattr(self, "_target"):
            if isinstance(self.to, str):
                try:
                    self._target = self.target_registry.get_model(self.to)
                except LookupError:
                    self._target = (
                        self.target_registry.models.get(self.to)
                        or self.target_registry.reflected[self.to]
                    )
            else:
                self._target = self.to
        return self._target

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return self.ForeignKeyValidator(**kwargs)

    @property
    def related_columns(self) -> dict[str, sqlalchemy.Column | None]:
        """Return target columns used by the relation mapping.

        Composite foreign keys can point to multiple target columns. When
        explicit `related_fields` are not provided, the target model primary-key
        columns are used.

        Returns:
            dict[str, sqlalchemy.Column | None]: Mapping of target column names to
            SQLAlchemy columns where available.
        """
        target = self.target
        columns: dict[str, sqlalchemy.Column | None] = {}
        if self.related_fields:
            for field_name in self.related_fields:
                if field_name in target.meta.fields:
                    for column in target.meta.field_to_columns[field_name]:
                        columns[column.key] = column
                else:
                    columns[field_name] = None
            return columns
        keys = tuple(getattr(target, "pknames", ())) or tuple(getattr(target, "pkcolumns", ()))
        if not keys:
            keys = (getattr(target, "pkname", "id"),)
        table = getattr(target, "_table", None)
        for key in keys:
            column = None
            if table is not None:
                column = getattr(table.c, key, None)
            columns[key] = column
        return columns

    def get_fk_name(self, name: str) -> str:
        fk_name = f"fk_{self.owner.meta.tablename}_{self.target.meta.tablename}_{name}"
        return fk_name[:CHAR_LIMIT]

    def get_fkindex_name(self, name: str) -> str:
        fk_name = f"fkindex_{self.owner.meta.tablename}_{self.target.meta.tablename}_{name}"
        return fk_name[:CHAR_LIMIT]

    def get_fk_field_name(self, name: str, fieldname: str) -> str:
        if len(self.related_columns) == 1:
            return name
        return f"{name}_{fieldname}"

    def get_fk_column_name(self, name: str, fieldname: str) -> str:
        name = self.column_name or name
        if len(self.related_columns) == 1:
            return name
        return f"{name}_{fieldname}"

    def get_column_names(self, name: str) -> tuple[str, ...]:
        return tuple(
            self.get_fk_field_name(name, field_name) for field_name in self.related_columns
        )

    def from_fk_field_name(self, name: str, fieldname: str) -> str:
        if len(self.related_columns) == 1:
            return next(iter(self.related_columns.keys()))
        return fieldname.removeprefix(f"{name}_")

    def get_columns(self, name: str) -> typing.Sequence[sqlalchemy.Column]:
        target = self.target
        columns: list[sqlalchemy.Column] = []
        for related_key, related_column in self.related_columns.items():
            related_field = target.fields[related_key]
            related_type = (
                related_column.type
                if related_column is not None
                else related_field.get_column_type()
            )
            related_name = (
                getattr(related_column, "name", None) or related_field.column_name or related_key
            )
            related_nullable = (
                related_column.nullable if related_column is not None else related_field.null
            )
            columns.append(
                sqlalchemy.Column(
                    key=self.get_fk_field_name(name, related_key),
                    name=self.get_fk_column_name(name, related_name),
                    type_=related_type,
                    nullable=self.null or related_nullable,
                    primary_key=self.primary_key,
                    autoincrement=False,
                )
            )
        return columns

    def get_column(self, name: str) -> sqlalchemy.Column:
        columns = tuple(self.get_columns(name))
        if len(columns) != 1:
            raise RuntimeError(
                f"Foreign key '{name}' on '{self.owner.__name__}' maps to multiple database columns."
            )
        return columns[0]

    def get_global_constraints(
        self,
        name: str,
        columns: typing.Sequence[sqlalchemy.Column],
        *,
        schema: str | None = None,
    ) -> typing.Sequence[sqlalchemy.Constraint | sqlalchemy.Index]:
        """Build cross-table constraints and indexes for the foreign key columns.

        Args:
            name: Logical field name on the owning model.
            columns: Physical columns generated for the relation.
            schema: Optional schema override for the target table reference.

        Returns:
            typing.Sequence[sqlalchemy.Constraint | sqlalchemy.Index]:
                SQLAlchemy constraints and indexes that should be attached to
                the owning table.
        """
        owner_registry = getattr(self.owner.meta, "registry", None)
        target = self.target
        target_registry = getattr(target.meta, "registry", None)
        owner_database = getattr(self.owner, "database", None)
        target_database = getattr(target, "database", None)
        use_constraint = not (
            self.no_constraint
            or (
                owner_registry not in (None, False)
                and target_registry not in (None, False)
                and owner_registry is not target_registry
            )
            or (
                owner_database is not None
                and target_database is not None
                and owner_database is not target_database
            )
        )
        constraints: list[sqlalchemy.Constraint | sqlalchemy.Index] = []
        if use_constraint:
            table_name = target.meta.tablename
            if schema is not None:
                table_name = f"{schema}.{table_name}"
            constraints.append(
                sqlalchemy.schema.ForeignKeyConstraint(
                    columns,
                    [
                        f"{table_name}.{self.from_fk_field_name(name, column.key)}"
                        for column in columns
                    ],
                    ondelete=self.on_delete,
                    onupdate=self.on_update,
                    name=self.get_fk_name(name),
                )
            )
        if self.unique or self.index:
            constraints.append(
                sqlalchemy.Index(
                    self.get_fkindex_name(name),
                    *columns,
                    unique=self.unique,
                )
            )
        return constraints

    def clean(
        self, name: str, value: typing.Any, *, for_query: bool = False
    ) -> dict[str, typing.Any]:
        del for_query
        cleaned: dict[str, typing.Any] = {}
        related_keys = tuple(self.related_columns.keys())
        column_names = self.get_column_names(name)

        if value is None:
            for column_name in column_names:
                cleaned[column_name] = None
            return cleaned

        target = self.target
        if isinstance(value, dict):
            for related_key, column_name in zip(related_keys, column_names, strict=False):
                if related_key in value:
                    cleaned[column_name] = value[related_key]
                elif column_name in value:
                    cleaned[column_name] = value[column_name]
            return cleaned

        if isinstance(value, target):
            for related_key, column_name in zip(related_keys, column_names, strict=False):
                cleaned[column_name] = getattr(value, related_key, None)
            return cleaned

        if hasattr(value, "__db_model__"):
            value_cls = value.__class__
            if (
                getattr(value_cls, "is_proxy_model", False)
                and getattr(value_cls, "parent", None) is target
            ):
                for related_key, column_name in zip(related_keys, column_names, strict=False):
                    cleaned[column_name] = getattr(value, related_key, None)
                return cleaned

        pk_value = getattr(value, "pk", None) if hasattr(value, "pk") else None
        if isinstance(pk_value, dict):
            return self.clean(name, pk_value)
        if pk_value is not None and len(column_names) == 1:
            cleaned[column_names[0]] = pk_value
            return cleaned

        if len(column_names) == 1:
            cleaned[column_names[0]] = value
            return cleaned

        raise ValueError(f"Cannot handle composite foreign key value {value!r}.")

    def modify_input(self, name: str, kwargs: dict[str, typing.Any]) -> None:
        if name in kwargs:
            return

        column_names = self.get_column_names(name)
        if len(column_names) <= 1:
            return

        payload: dict[str, typing.Any] = {}
        for column_name in column_names:
            if column_name in kwargs:
                payload[self.from_fk_field_name(name, column_name)] = kwargs.pop(column_name)

        if not payload:
            return
        if len(payload) != len(column_names):
            raise ValueError("Cannot update the foreign key partially")
        kwargs[name] = payload

    async def pre_save_callback(
        self,
        value: typing.Any,
        original_value: typing.Any,
        is_update: bool,
    ) -> dict[str, typing.Any]:
        """Save nested related objects before persisting the owning row.

        The callback allows callers to pass an unsaved related model instance or
        a dictionary payload. When necessary, the related object is saved first
        and the method returns the concrete foreign-key column values to persist
        on the owning model.

        Args:
            value: Current relation value being persisted.
            original_value: Previous relation value used during updates.
            is_update: Whether the owning model is performing an update.

        Returns:
            dict[str, typing.Any]: Database-ready foreign-key column payload.
        """
        target = self.target
        if value is None or (isinstance(value, dict) and not value):
            value = original_value

        if isinstance(value, target):
            if (
                getattr(value, "_saffier_save_in_progress", False)
                or getattr(value, "pk", None) is not None
            ):
                return self.clean(self.name, value, for_query=False)
            await value.save()
            return self.clean(self.name, value, for_query=False)

        if hasattr(value, "__db_model__"):
            value_cls = value.__class__
            if (
                getattr(value_cls, "is_proxy_model", False)
                and getattr(value_cls, "parent", None) is target
            ):
                if (
                    getattr(value, "_saffier_save_in_progress", False)
                    or getattr(value, "pk", None) is not None
                ):
                    return self.clean(self.name, value, for_query=False)
                await value.save()
                return self.clean(self.name, value, for_query=False)

        if isinstance(value, dict):
            return await self.pre_save_callback(
                target(**value),
                original_value=None,
                is_update=is_update,
            )

        if hasattr(value, "pk") and getattr(value, "pk", None) is not None:
            return self.clean(self.name, value, for_query=False)

        if value is None:
            return {}
        return {self.name: value}

    def expand_relationship(self, value: typing.Any) -> typing.Any:
        """Normalize relation values into lightweight target model instances.

        Raw primary-key values, dictionaries, proxy models, and already-loaded
        target instances are all accepted so callers can assign foreign keys in a
        natural way while the ORM preserves a consistent in-memory shape.

        Args:
            value: Incoming relation value.

        Returns:
            typing.Any: Target model instance or `None`.
        """
        if value is None:
            return None
        target = self.target
        related_columns = tuple(self.related_columns.keys())
        if isinstance(value, target):
            if (
                self.null
                and related_columns
                and all(
                    key in value.__dict__ and getattr(value, key) is None
                    for key in related_columns
                )
            ):
                return None
            return value
        if hasattr(value, "__db_model__"):
            value_cls = value.__class__
            if (
                getattr(value_cls, "is_proxy_model", False)
                and getattr(value_cls, "parent", None) is target
            ):
                if (
                    self.null
                    and related_columns
                    and all(
                        key in value.__dict__ and getattr(value, key) is None
                        for key in related_columns
                    )
                ):
                    return None
                return value
        if isinstance(value, dict):
            return target(**value)
        if hasattr(value, "pk"):
            pk_value = value.pk
            if isinstance(pk_value, dict):
                return target(pk=pk_value)
            return target(pk=pk_value)
        return target(pk=value)

    def is_cross_db(self, owner_database: typing.Any | None = None) -> bool:
        if owner_database is None:
            owner_database = getattr(self.owner, "database", None)
            if owner_database is None:
                owner_registry = getattr(getattr(self.owner, "meta", None), "registry", None)
                owner_database = getattr(owner_registry, "database", None)

        target = self.target
        target_database = getattr(target, "database", None)
        if target_database is None:
            target_registry = getattr(getattr(target, "meta", None), "registry", None)
            target_database = getattr(target_registry, "database", None)

        if owner_database is None or target_database is None:
            return False

        return str(owner_database.url) != str(target_database.url)

    def get_related_model_for_admin(self) -> typing.Any | None:
        target = self.target
        registry = getattr(getattr(target, "meta", None), "registry", None)
        admin_models = getattr(registry, "admin_models", ())
        if registry and target.__name__ in admin_models:
            return target
        return None


class ManyToManyField(Field):
    """Virtual field describing a many-to-many relation via a through model.

    A many-to-many field never maps directly to columns on the owning model.
    Instead it manages or creates an intermediate through model, exposes a
    `Relation` descriptor for runtime access, and carries the metadata needed to
    build reverse relation names, embedded through objects, and auto-generated
    junction table definitions.
    """

    is_virtual: bool = True

    def __init__(
        self,
        to: type["Model"] | str,
        through: type["Model"] | str | None = None,
        through_tablename: str | type[NEW_M2M_NAMING] | None = NEW_M2M_NAMING,
        embed_through: str | bool = False,
        to_foreign_key: str = "",
        from_foreign_key: str = "",
        **kwargs: typing.Any,
    ):
        if through_tablename is not None and (
            not isinstance(through_tablename, str) and through_tablename is not NEW_M2M_NAMING
        ):
            raise FieldDefinitionError(
                '"through_tablename" must be NEW_M2M_NAMING or a non-empty string.'
            )
        if isinstance(through_tablename, str) and not through_tablename.strip():
            raise FieldDefinitionError('"through_tablename" cannot be an empty string.')
        if embed_through and isinstance(embed_through, str) and "__" in embed_through:
            raise FieldDefinitionError('"embed_through" cannot contain "__".')

        if "null" in kwargs:
            terminal.write_warning("Declaring `null` on a ManyToMany relationship has no effect.")

        related_name = kwargs.pop("related_name", None)
        super().__init__(null=True, **kwargs)
        self.to = to
        self.through = through
        self.through_tablename = through_tablename
        self.embed_through = embed_through
        self.related_name = related_name
        self.from_foreign_key = from_foreign_key
        self.to_foreign_key = to_foreign_key
        self.reverse_name = ""

        if self.related_name not in (None, False):
            assert isinstance(self.related_name, str), "related_name must be a string."

        if isinstance(self.related_name, str):
            self.related_name = self.related_name.lower()

    @property
    def target(self) -> typing.Any:
        """Resolve and cache the many-to-many target model class.

        Returns:
            typing.Any: Target model class for the relation.
        """
        if not hasattr(self, "_target"):
            if isinstance(self.to, str):
                self._target = (
                    self.registry.models.get(self.to) or self.registry.reflected[self.to]
                )
            else:
                self._target = self.to
        return self._target

    def get_column(self, name: str) -> sqlalchemy.Column:
        target = self.target
        to_field = target.fields[target.pkname]

        column_type = to_field.get_column_type()
        constraints = [
            sqlalchemy.schema.ForeignKey(
                f"{target.meta.tablename}.{target.pkname}",
                ondelete=saffier.CASCADE,
                onupdate=saffier.CASCADE,
                name=self.get_fk_name(name=name),
            )
        ]
        return sqlalchemy.Column(name, column_type, *constraints, nullable=self.null)

    def add_model_to_register(self, model: type["Model"]) -> None:
        """Register an auto-generated through model on the owning registry.

        Args:
            model: Through model created for the relation.
        """
        self.registry.models[model.__name__] = model

    def get_fk_name(self, name: str) -> str:
        """Build a stable FK constraint name for the through table.

        Args:
            name: Local field or column name participating in the constraint.

        Returns:
            str: Constraint name truncated to common identifier limits.
        """
        fk_name = f"fk_{self.owner.meta.tablename}_{self.target.meta.tablename}_{self.target.pkname}_{name}"
        if not len(fk_name) > CHAR_LIMIT:
            return fk_name
        return fk_name[:CHAR_LIMIT]

    def create_through_model(self) -> typing.Any:
        """Create or normalize the through model used to persist the relation.

        Returns:
            typing.Any: Concrete through model class used by the relation.

        Raises:
            ImproperlyConfigured: If an explicit through model does not expose a
                valid integer `id` primary key.
        """
        self.to = typing.cast(type["Model"], self.target)

        if self.through:
            if isinstance(self.through, str):
                registry = self.owner.meta.registry
                self.through = (
                    registry.models.get(self.through) or registry.reflected[self.through]
                )

            if not self.from_foreign_key:
                candidates = [
                    field_name
                    for field_name, field in self.through.fields.items()
                    if isinstance(field, ForeignKey) and field.target is self.owner
                ]
                if len(candidates) == 1:
                    self.from_foreign_key = candidates[0]
            if not self.to_foreign_key:
                candidates = [
                    field_name
                    for field_name, field in self.through.fields.items()
                    if isinstance(field, ForeignKey) and field.target is self.to
                ]
                if len(candidates) == 1:
                    self.to_foreign_key = candidates[0]

            # M2M through models in Saffier are always required to expose an
            # auto-incrementing integer "id" primary key.
            id_field = self.through.fields.get("id")
            if id_field is None:
                has_non_id_pk = any(
                    field.primary_key
                    for field_name, field in self.through.fields.items()
                    if field_name != "id"
                )
                if has_non_id_pk:
                    raise ImproperlyConfigured(
                        "ManyToMany through models must use an auto-incrementing 'id' primary key."
                    )
                id_field = saffier.IntegerField(primary_key=True, autoincrement=True)
                id_field.owner = self.through
                id_field.registry = self.through.meta.registry
                id_field.name = "id"
                self.through.fields["id"] = id_field
                self.through.meta.fields["id"] = id_field
                self.through.meta.fields_mapping["id"] = id_field
                self.through.meta.pk = id_field
                self.through.meta.pk_attribute = "id"
                self.through.pkname = "id"
                self.through._table = None
                self.through.__proxy_model__ = None
            elif not id_field.primary_key:
                raise ImproperlyConfigured(
                    "ManyToMany through models must define 'id' as the primary key."
                )
            elif not isinstance(id_field, (IntegerField, SmallIntegerField, BigIntegerField)):
                raise ImproperlyConfigured(
                    "ManyToMany through model 'id' primary key must be an integer type."
                )
            else:
                id_field.autoincrement = True

            self.through.meta.is_multi = True
            if not self.from_foreign_key:
                self.from_foreign_key = self.owner.__name__.lower()
            if not self.to_foreign_key:
                self.to_foreign_key = self.to.__name__.lower()
            self.through.meta.multi_related = [self.to_foreign_key]
            return self.through

        owner_name = self.owner.__name__
        to_name = self.to.__name__
        if not self.from_foreign_key:
            self.from_foreign_key = owner_name.lower()
        if not self.to_foreign_key:
            self.to_foreign_key = to_name.lower()
        class_name = f"{owner_name}{self.name.capitalize()}Through"
        if self.through_tablename is None or self.through_tablename is NEW_M2M_NAMING:
            tablename = class_name.lower()
        else:
            tablename = self.through_tablename.format(field=self).lower()
        if self.owner.meta.table_prefix:
            tablename = f"{self.owner.meta.table_prefix}_{tablename}"

        new_meta_namespace = {
            "tablename": tablename,
            "registry": self.owner.meta.registry,
            "is_multi": True,
            "multi_related": [self.to_foreign_key],
            "unique_together": [(self.from_foreign_key, self.to_foreign_key)],
        }

        new_meta = type("MetaInfo", (), new_meta_namespace)

        to_related_name = (
            f"{self.related_name}"
            if self.related_name
            else (
                f"{to_name.lower()}_{owner_name.lower()}{to_name.lower()}"
                if self.unique
                else f"{to_name.lower()}_{owner_name.lower()}{to_name.lower()}s_set"
            )
        )
        self.reverse_name = to_related_name if to_related_name is not False else ""

        through_model = type(
            class_name,
            (saffier.Model,),
            {
                "Meta": new_meta,
                "id": saffier.IntegerField(primary_key=True, autoincrement=True),
                f"{self.from_foreign_key}": ForeignKey(
                    self.owner,
                    on_delete=saffier.CASCADE,
                    index=self.index,
                    null=True,
                    related_name=False,
                ),
                f"{self.to_foreign_key}": ForeignKey(
                    self.to,
                    on_delete=saffier.CASCADE,
                    unique=self.unique,
                    index=self.index,
                    null=True,
                    embed_parent=(
                        (self.from_foreign_key, self.embed_through or "")
                        if self.embed_through is not False
                        else None
                    ),
                    related_name=(False if self.related_name is False else to_related_name),
                ),
            },
        )
        self.through = typing.cast(type["Model"], through_model)

        self.add_model_to_register(self.through)
        tenant_models = getattr(self.registry, "tenant_models", None)
        if tenant_models is not None and (
            getattr(self.owner.meta, "is_tenant", False)
            or getattr(self.to.meta, "is_tenant", False)
        ):
            tenant_models[self.through.__name__] = self.through
            if getattr(self.owner.meta, "register_default", None) is False:
                self.registry.models.pop(self.through.__name__, None)


ManyToMany = ManyToManyField


class RefForeignKey(ForeignKey):
    """Foreign key variant used for explicit reference-style declarations.

    `RefForeignKey` can operate in two modes. In normal mode it behaves like a
    regular foreign key. In model-reference mode it becomes a virtual field that
    stages lightweight reference objects and later persists them through the
    reverse relation declared by the referenced `ModelRef` type.
    """

    def __init__(
        self,
        to: type["Model"] | str,
        *,
        ref_field: str | None = None,
        **kwargs: typing.Any,
    ) -> None:
        self.ref_field = ref_field
        self.model_ref = None
        if (
            isinstance(to, type)
            and hasattr(to, "__model_ref_fields__")
            and hasattr(to, "__related_name__")
        ):
            if not getattr(to, "__related_name__", None):
                raise ModelReferenceError(
                    detail="'__related_name__' must be declared when subclassing ModelRef."
                )
            self.model_ref = to
            self.is_virtual = True
        super().__init__(to=to, **kwargs)

    @property
    def is_model_reference(self) -> bool:
        """Return whether the field currently behaves as a virtual model reference.

        Returns:
            bool: `True` when the field is staging `ModelRef` objects instead of
            storing a direct foreign key column.
        """
        return self.model_ref is not None

    def has_column(self) -> bool:
        return not self.is_model_reference and super().has_column()

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        if self.is_model_reference:
            return Any(**kwargs)
        return super().get_validator(**kwargs)

    def get_column(self, name: str) -> sqlalchemy.Column:
        if self.is_model_reference:
            raise RuntimeError(f"Virtual field '{name}' does not map to a database column.")
        return super().get_column(name)

    def expand_relationship(self, value: typing.Any) -> typing.Any:
        if self.is_model_reference:
            return value
        return super().expand_relationship(value)

    def _normalize_model_ref(self, value: typing.Any) -> typing.Any:
        if value is None:
            return None
        if isinstance(value, self.model_ref):
            return value
        if isinstance(value, dict):
            return self.model_ref(**value)
        raise ModelReferenceError(
            detail=(
                f"RefForeignKey '{self.name}' expects '{self.model_ref.__name__}' instances "
                "or dictionaries."
            )
        )

    def set_value(self, instance: typing.Any, field_name: str, value: typing.Any) -> None:
        if not self.is_model_reference:
            instance.__dict__[field_name] = value
            return

        if value is None:
            instance.__dict__[field_name] = None
            return

        values: typing.Sequence[typing.Any]
        if isinstance(value, typing.Sequence) and not isinstance(value, (str, bytes, bytearray)):
            values = value
        else:
            values = [value]

        instance.__dict__[field_name] = [
            model_ref
            for item in values
            if (model_ref := self._normalize_model_ref(item)) is not None
        ]

    def get_value(self, instance: typing.Any, field_name: str) -> list[typing.Any]:
        value = instance.__dict__.get(field_name)
        if value is None:
            return []
        return list(value)

    async def persist_references(self, instance: typing.Any, value: typing.Any) -> None:
        """Persist staged `ModelRef` objects through the generated reverse relation.

        Args:
            instance: Parent model instance that owns the relation.
            value: Staged reference payload previously assigned to the field.
        """
        if not self.is_model_reference or not value:
            return

        related_name = self.model_ref.__related_name__
        relation = getattr(instance, related_name)
        references = value
        if not isinstance(references, typing.Sequence) or isinstance(
            references, (str, bytes, bytearray)
        ):
            references = [references]

        for reference in references:
            model_ref = self._normalize_model_ref(reference)
            if model_ref is None:
                continue
            await relation.create(**model_ref.model_dump())


class OneToOneField(ForeignKey):
    """Foreign-key field that enforces a unique reverse relationship.

    The field is implemented as a standard foreign key with `unique=True`, which
    gives it one-to-one semantics while reusing the full foreign-key machinery.
    """

    def __init__(self, to: type["Model"] | str, **kwargs: typing.Any):
        kwargs["unique"] = True
        super().__init__(to, **kwargs)

    def get_column(self, name: str) -> sqlalchemy.Column:
        return super().get_column(name)


OneToOne = OneToOneField


class ChoiceField(Field):
    """Field that stores enumerated values.

    The field accepts either a Python `Enum` subclass or a static list of choice
    values and maps them to a SQL enum type.
    """

    def __init__(
        self,
        choices: type[enum.Enum] | typing.Sequence[tuple[str, str] | tuple[str, int] | str | int],
        **kwargs: typing.Any,
    ) -> None:
        super().__init__(**kwargs)
        self.choices = choices

    def get_validator(self, **kwargs: typing.Any) -> Any:
        return Any(**kwargs)

    def _enum_name(self) -> str | None:
        owner = getattr(self, "owner", None)
        if owner is None or not self.name:
            return None

        table_name = getattr(getattr(owner, "meta", None), "tablename", owner.__name__.lower())
        return f"{table_name}_{self.name}_enum"

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        if isinstance(self.choices, type) and issubclass(self.choices, enum.Enum):
            return sqlalchemy.Enum(self.choices, name=self._enum_name())

        enum_values = [
            choice[0] if isinstance(choice, (tuple, list)) else choice for choice in self.choices
        ]
        return sqlalchemy.Enum(*[str(value) for value in enum_values], name=self._enum_name())


class CharChoiceField(Field):
    """Choice field stored as plain text rather than a SQL enum.

    This is useful when portability matters more than native enum constraints or
    when the database should not own the enum definition.
    """

    def __init__(
        self,
        choices: type[enum.Enum] | typing.Sequence[typing.Any],
        max_length: int | None = 30,
        **kwargs: typing.Any,
    ) -> None:
        super().__init__(**kwargs)
        self.choices = choices
        self.max_length = max_length

    def get_validator(self, **kwargs: typing.Any) -> Any:
        return Any(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        if self.max_length is None:
            return sqlalchemy.Text()
        return sqlalchemy.String(length=self.max_length)


class DecimalField(Field):
    """Fixed-precision numeric field backed by SQL `NUMERIC`/`DECIMAL`.

    The field preserves decimal precision and is appropriate for money-like
    values that should not be stored in a floating-point type.
    """

    def __init__(self, max_digits: int, decimal_places: int, **kwargs: typing.Any):
        assert max_digits, "max_digits is required"
        assert decimal_places, "decimal_places is required"
        self.max_digits = max_digits
        self.decimal_places = decimal_places
        super().__init__(**kwargs)

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Decimal(**kwargs)

    def get_column_type(self) -> sqlalchemy.Numeric:
        return sqlalchemy.Numeric(precision=self.max_digits, scale=self.decimal_places)

    def get_is_empty_clause(self, column: typing.Any) -> typing.Any:
        return sqlalchemy.or_(self.get_is_null_clause(column), column == decimal.Decimal("0"))


class UUIDField(Field):
    """Field that stores UUID values using the database UUID type.

    It is suitable for application-generated identifiers and public-facing keys.
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return UUID(**kwargs)

    def get_column_type(self) -> sqlalchemy.UUID:
        return sqlalchemy.UUID()


class PasswordField(CharField):
    """Character field that applies password-format validation.

    The storage type remains plain text; hashing and secret handling are left to
    the application layer.
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Password(**kwargs)

    def get_column_type(self) -> sqlalchemy.String:
        return sqlalchemy.String(length=self.validator.max_length)  # type: ignore


class IPAddressField(Field):
    """Field that stores IPv4 or IPv6 address values.

    The field normalizes values through the IP-address validator before
    persistence.
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return CoreIPAddress(**kwargs)

    def get_column_type(self) -> IPAddress:
        return IPAddress()


class EmailField(CharField):
    """Character field with e-mail address validation.

    It uses the same bounded string storage as `CharField`.
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Email(**kwargs)

    def get_column_type(self) -> sqlalchemy.String:
        return sqlalchemy.String(length=self.validator.max_length)  # type: ignore


class URLField(CharField):
    """Character field with absolute-URL validation.

    It validates scheme and network location before storing the value as text.
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return URL(**kwargs)

    def get_column_type(self) -> sqlalchemy.String:
        return sqlalchemy.String(length=self.validator.max_length)  # type: ignore


class BinaryField(Field):
    """Binary field for arbitrary bytes payloads.

    The field optionally enforces a maximum length and stores data in a SQL
    large-binary column.
    """

    def __init__(self, max_length: int | None = None, **kwargs: typing.Any):
        self.max_length = max_length
        super().__init__(**kwargs)

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        kwargs["max_length"] = self.max_length
        return Binary(**kwargs)

    def get_column_type(self) -> sqlalchemy.LargeBinary:
        return sqlalchemy.LargeBinary(length=self.max_length)

    def get_is_empty_clause(self, column: typing.Any) -> typing.Any:
        return sqlalchemy.or_(self.get_is_null_clause(column), column == b"")


class ExcludeField(Field):
    """Virtual field that reserves an attribute name without creating a column.

    It is primarily used for placeholders and internal relation plumbing where a
    model attribute must exist in metadata but should never be persisted.
    """

    is_virtual = True

    def __init__(self, **kwargs: typing.Any) -> None:
        kwargs.setdefault("null", True)
        kwargs.setdefault("read_only", True)
        kwargs.setdefault("exclude", True)
        super().__init__(**kwargs)

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Any(**kwargs)

    def get_column(self, name: str) -> sqlalchemy.Column:
        raise RuntimeError(f"Virtual field '{name}' does not map to a database column.")

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        raise RuntimeError("ExcludeField does not expose a column type.")


class PlaceholderField(ExcludeField):
    """Named placeholder field used by reverse-relation internals.

    Placeholder fields make reverse relation names visible in metadata without
    creating any database columns.
    """


class ComputedField(Field):
    """Virtual field whose value is resolved by getter/setter callbacks.

    Computed fields do not create database columns. They allow models to expose
    derived or delegated attributes while still participating in model dumps,
    admin marshalling, and assignment flows through explicit getter and setter
    callables.
    """

    is_virtual = True
    is_computed = True

    def __init__(
        self,
        *,
        getter: str | typing.Callable[..., typing.Any] | None = None,
        setter: str | typing.Callable[..., typing.Any] | None = None,
        fallback_getter: typing.Callable[..., typing.Any] | None = None,
        **kwargs: typing.Any,
    ) -> None:
        kwargs.setdefault("null", True)
        kwargs.setdefault("read_only", setter is None)
        kwargs.setdefault("exclude", True)
        super().__init__(**kwargs)
        self.getter = getter
        self.setter = setter
        self.fallback_getter = fallback_getter

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Any(**kwargs)

    def get_column(self, name: str) -> sqlalchemy.Column:
        raise RuntimeError(f"Computed field '{name}' does not map to a database column.")

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        raise RuntimeError("ComputedField does not expose a column type.")

    def _resolve_callable(
        self,
        instance: typing.Any,
        func: str | typing.Callable[..., typing.Any] | None,
    ) -> typing.Callable[..., typing.Any] | None:
        if func is None:
            return None
        if isinstance(func, str):
            return getattr(instance, func)
        return func

    @staticmethod
    def _call_with_supported_signatures(
        callback: typing.Callable[..., typing.Any],
        field: "ComputedField",
        instance: typing.Any,
        owner: type["Model"],
        value: typing.Any = None,
        *,
        include_value: bool = False,
    ) -> typing.Any:
        call_signatures = [
            (field, instance, owner),
            (field, instance),
            (instance,),
            (),
        ]
        if include_value:
            call_signatures = [
                (field, instance, value, owner),
                (field, instance, value),
                (instance, value),
                (value,),
            ]

        for args in call_signatures:
            try:
                return callback(*args)
            except TypeError:
                continue
        if include_value:
            return callback(field, instance, value, owner)
        return callback(field, instance, owner)

    def get_value(self, instance: typing.Any, name: str) -> typing.Any:
        if name in instance.__dict__:
            return instance.__dict__[name]

        owner = instance.__class__
        getter = self._resolve_callable(instance, self.getter)
        if getter is not None:
            value = self._call_with_supported_signatures(getter, self, instance, owner)
            if value is not None:
                return value

        fallback = self._resolve_callable(instance, self.fallback_getter)
        if fallback is not None:
            return self._call_with_supported_signatures(fallback, self, instance, owner)

        raise AttributeError(name)

    def set_value(self, instance: typing.Any, name: str, value: typing.Any) -> None:
        owner = instance.__class__
        setter = self._resolve_callable(instance, self.setter)
        if setter is None:
            instance.__dict__[name] = value
            return

        result = self._call_with_supported_signatures(
            setter,
            self,
            instance,
            owner,
            value,
            include_value=True,
        )
        if result is not None:
            instance.__dict__[name] = result


class FileField(CharField):
    """Text field intended for file path or storage reference values.

    It is a semantic alias of `CharField` with a file-oriented default length.
    """

    def __init__(self, max_length: int = 255, **kwargs: typing.Any) -> None:
        kwargs.setdefault("max_length", max_length)
        super().__init__(**kwargs)


class ImageField(FileField):
    """File-like text field intended for image references.

    The field does not inspect image contents; it simply signals image intent in
    model definitions.
    """


class PGArrayField(Field):
    """PostgreSQL `ARRAY` field with mutable list tracking.

    The field wraps the array type in SQLAlchemy's `MutableList` helper so
    in-place list mutations are detected and persisted.
    """

    def __init__(self, item_type: sqlalchemy.types.TypeEngine, **kwargs: typing.Any) -> None:
        if not isinstance(item_type, sqlalchemy.types.TypeEngine):
            raise AssertionError("item_type must be a SQLAlchemy TypeEngine instance.")
        self.item_type = item_type
        super().__init__(**kwargs)

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Any(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return typing.cast(
            sqlalchemy.types.TypeEngine,
            MutableList.as_mutable(postgresql.ARRAY(self.item_type)),
        )
