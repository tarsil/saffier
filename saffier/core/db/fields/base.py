import copy
import enum
import typing
from datetime import date, datetime

import sqlalchemy
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.mutable import MutableList

import saffier
from saffier.contrib.sqlalchemy.fields import IPAddress
from saffier.core.db.constants import CASCADE, NEW_M2M_NAMING, OLD_M2M_NAMING, RESTRICT, SET_NULL
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
    """
    Base field for the model declaration fields.
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
        self.owner = kwargs.pop("owner", None)
        self.registry = kwargs.pop("registry", None)
        self.name = kwargs.pop("name", "")
        self.inherit = kwargs.pop("inherit", True)
        self.no_copy = kwargs.pop("no_copy", False)
        self.exclude = kwargs.pop("exclude", False)
        self.server_onupdate = kwargs.pop("server_onupdate", None)
        self.autoincrement = kwargs.pop("autoincrement", False)
        self.secret = kwargs.pop("secret", False)

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
            default=self.default_value,
            comment=self.comment,
            server_default=self.server_default,
        )

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return SaffierField(**kwargs)  # pragma: no cover

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        raise NotImplementedError()  # pragma: no cover

    def get_constraints(self) -> typing.Any:
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

    def modify_input(self, name: str, kwargs: dict[str, typing.Any]) -> None:
        del name, kwargs

    def raise_for_non_default(self, default: typing.Any, server_default: typing.Any) -> typing.Any:
        has_default: bool = True
        has_server_default: bool = True

        if default is None or default is False:
            has_default = False
        if server_default is None or server_default is False:
            has_server_default = False

        if (
            not isinstance(self, (IntegerField, BigIntegerField, SmallIntegerField))
            and not has_default
            and not has_server_default
        ):
            raise ValueError(
                "Primary keys other then IntegerField and BigIntegerField, must provide a default or a server_default."
            )


class CharField(Field):
    """
    Representation a StringField text with a max_length.
    """

    def __init__(self, **kwargs: typing.Any) -> None:
        assert "max_length" in kwargs, "max_length is required"
        super().__init__(**kwargs)

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return String(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.String(length=self.validator.max_length)  # type: ignore


class TextField(Field):
    """
    Representation of a TextField for a big length of text
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return String(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.Text()


class IntegerField(Field):
    """
    Representation of an IntegerField
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Integer(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.Integer()


class SmallIntegerField(IntegerField):
    """
    Representation of a SmallIntegerField.
    """

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.SmallInteger()


class FloatField(Field):
    """
    Representation of a Decimal floating field
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Float(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.Float()


class BigIntegerField(Field):
    """
    Represents a BigIntegerField
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Integer(**kwargs)

    def get_column_type(self) -> typing.Any:
        return sqlalchemy.BigInteger()


class BooleanField(Field):
    """
    Representation of a boolean
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Boolean(**kwargs)

    def get_column_type(self) -> sqlalchemy.types.TypeEngine:
        return sqlalchemy.Boolean()


class AutoNowMixin(Field):
    """
    Represents a date time with defaults for automatic now()
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
    """
    Representation of a datetime
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        if self.auto_now_add or self.auto_now:
            kwargs["default"] = datetime.now
        return DateTime(**kwargs)

    def get_column_type(self) -> sqlalchemy.DateTime:
        return sqlalchemy.DateTime()


class DateField(AutoNowMixin):
    """
    Representation of a Date
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        if self.auto_now_add or self.auto_now:
            kwargs["default"] = date.today
        return Date(**kwargs)

    def get_column_type(self) -> sqlalchemy.Date:
        return sqlalchemy.Date()


class TimeField(Field):
    """
    Representation of time
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Time(**kwargs)

    def get_column_type(self) -> sqlalchemy.Time:
        return sqlalchemy.Time()


class DurationField(Field):
    """
    Representation of a duration/timedelta.
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Duration(**kwargs)

    def get_column_type(self) -> sqlalchemy.Interval:
        return sqlalchemy.Interval()


class JSONField(Field):
    """
    JSON Representation of an object field
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Any(**kwargs)

    def get_column_type(self) -> sqlalchemy.JSON:
        return sqlalchemy.JSON()


class CompositeField(Field):
    """
    Virtual field that groups multiple model fields under a single logical attribute.

    It can expose existing fields by name and/or inject embedded fields declared inline.
    """

    is_virtual: bool = True

    def __init__(
        self,
        *,
        inner_fields: typing.Any = (),
        prefix_embedded: str = "",
        absorb_existing_fields: bool = False,
        model: typing.Any = None,
        **kwargs: typing.Any,
    ) -> None:
        kwargs.setdefault("null", True)
        super().__init__(**kwargs)
        self.inner_fields = inner_fields
        self.prefix_embedded = prefix_embedded
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
    """
    ForeignKey field object
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
        assert on_delete is not None, "on_delete must not be null."

        if on_delete == SET_NULL and not null:
            raise AssertionError("When SET_NULL is enabled, null must be True.")

        if on_update and (on_update == SET_NULL and not null):
            raise AssertionError("When SET_NULL is enabled, null must be True.")

        primary_key = bool(kwargs.pop("primary_key", False))
        index = bool(kwargs.pop("index", False))
        unique = bool(kwargs.pop("unique", False))
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
    def target(self) -> typing.Any:
        if not hasattr(self, "_target"):
            if isinstance(self.to, str):
                try:
                    self._target = self.registry.get_model(self.to)
                except LookupError:
                    self._target = self.registry.models.get(self.to) or self.registry.reflected[
                        self.to
                    ]
            else:
                self._target = self.to
        return self._target

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return self.ForeignKeyValidator(**kwargs)

    def get_column(self, name: str) -> sqlalchemy.Column:
        target = self.target
        to_field = target.fields[target.pkname]

        column_type = to_field.get_column_type()
        owner_registry = getattr(self.owner.meta, "registry", None)
        target_registry = getattr(target.meta, "registry", None)
        owner_database = getattr(self.owner, "database", None)
        target_database = getattr(target, "database", None)
        use_constraint = not (
            self.no_constraint
            or (owner_registry not in (None, False) and target_registry not in (None, False) and owner_registry is not target_registry)
            or (owner_database is not None and target_database is not None and owner_database is not target_database)
        )
        constraints = []
        if use_constraint:
            constraints.append(
                sqlalchemy.schema.ForeignKey(
                    f"{target.meta.tablename}.{target.pkname}",
                    ondelete=self.on_delete,
                    onupdate=self.on_update,
                    name=f"fk_{self.owner.meta.tablename}_{target.meta.tablename}"
                    f"_{target.pkname}_{name}",
                )
            )
        return sqlalchemy.Column(
            name,
            column_type,
            *constraints,
            nullable=self.null,
            index=self.index,
            unique=self.unique,
        )

    def expand_relationship(self, value: typing.Any) -> typing.Any:
        if value is None and self.null:
            return None
        target = self.target
        if isinstance(value, target):
            if self.null and getattr(value, "pk", None) is None:
                return None
            return value
        if hasattr(value, "__db_model__"):
            value_cls = value.__class__
            if (
                getattr(value_cls, "is_proxy_model", False)
                and getattr(value_cls, "parent", None) is target
            ):
                if self.null and getattr(value, "pk", None) is None:
                    return None
                return value
        return target(pk=value)


class ManyToManyField(Field):
    """
    Representation of a ManyToManyField based on a foreignkey.
    """

    is_virtual: bool = True

    def __init__(
        self,
        to: type["Model"] | str,
        through: type["Model"] | str | None = None,
        through_tablename: str | type[NEW_M2M_NAMING] | None = NEW_M2M_NAMING,
        embed_through: str | bool = False,
        **kwargs: typing.Any,
    ):
        if through_tablename is OLD_M2M_NAMING:
            raise FieldDefinitionError(
                '"through_tablename" no longer supports OLD_M2M_NAMING in Saffier. '
                "Use NEW_M2M_NAMING or a non-empty string."
            )
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
        self.from_foreign_key = ""
        self.to_foreign_key = ""
        self.reverse_name = ""

        if self.related_name not in (None, False):
            assert isinstance(self.related_name, str), "related_name must be a string."

        if isinstance(self.related_name, str):
            self.related_name = self.related_name.lower()

    @property
    def target(self) -> typing.Any:
        if not hasattr(self, "_target"):
            if isinstance(self.to, str):
                self._target = self.registry.models.get(self.to) or self.registry.reflected[self.to]
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
        """
        Adds the model to the registry to make sure it can be generated by the Migrations
        """
        self.registry.models[model.__name__] = model

    def get_fk_name(self, name: str) -> str:
        """
        Builds the fk name for the engine.
        Engines have a limitation of the foreign key being bigger than 63
        characters.
        if that happens, we need to assure it is small.
        """
        fk_name = f"fk_{self.owner.meta.tablename}_{self.target.meta.tablename}_{self.target.pkname}_{name}"
        if not len(fk_name) > CHAR_LIMIT:
            return fk_name
        return fk_name[:CHAR_LIMIT]

    def create_through_model(self) -> typing.Any:
        """
        Creates the default empty through model.

        Generates a middle model based on the owner of the field and the field itself and adds
        it to the main registry to make sure it generates the proper models and migrations.
        """
        self.to = typing.cast(type["Model"], self.target)

        if self.through:
            if isinstance(self.through, str):
                registry = self.owner.meta.registry
                self.through = registry.models.get(self.through) or registry.reflected[self.through]

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
        self.from_foreign_key = owner_name.lower()
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
            getattr(self.owner.meta, "is_tenant", False) or getattr(self.to.meta, "is_tenant", False)
        ):
            tenant_models[self.through.__name__] = self.through
            if getattr(self.owner.meta, "register_default", None) is False:
                self.registry.models.pop(self.through.__name__, None)


ManyToMany = ManyToManyField


class RefForeignKey(ForeignKey):
    """
    ForeignKey variant used for explicit reference-style declarations.
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
    """
    Representation of a one to one field.
    """

    def __init__(self, to: type["Model"] | str, **kwargs: typing.Any):
        kwargs["unique"] = True
        super().__init__(to, **kwargs)

    def get_column(self, name: str) -> sqlalchemy.Column:
        target = self.target
        to_field = target.fields[target.pkname]

        column_type = to_field.get_column_type()
        owner_registry = getattr(self.owner.meta, "registry", None)
        target_registry = getattr(target.meta, "registry", None)
        owner_database = getattr(self.owner, "database", None)
        target_database = getattr(target, "database", None)
        use_constraint = not (
            self.no_constraint
            or (owner_registry not in (None, False) and target_registry not in (None, False) and owner_registry is not target_registry)
            or (owner_database is not None and target_database is not None and owner_database is not target_database)
        )
        constraints = []
        if use_constraint:
            constraints.append(
                sqlalchemy.schema.ForeignKey(
                    f"{target.meta.tablename}.{target.pkname}",
                    ondelete=self.on_delete,
                    onupdate=self.on_update,
                )
            )
        return sqlalchemy.Column(
            name,
            column_type,
            *constraints,
            nullable=self.null,
            unique=True,
        )


OneToOne = OneToOneField


class ChoiceField(Field):
    """
    Representation of an Enum
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
    """
    Choice field stored as character values.
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
    """
    Representation of a DecimalField
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


class UUIDField(Field):
    """
    Representation of UUID
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return UUID(**kwargs)

    def get_column_type(self) -> sqlalchemy.UUID:
        return sqlalchemy.UUID()


class PasswordField(CharField):
    """
    Representation of a Password
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Password(**kwargs)

    def get_column_type(self) -> sqlalchemy.String:
        return sqlalchemy.String(length=self.validator.max_length)  # type: ignore


class IPAddressField(Field):
    """
    Representation of UUUID
    """

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return CoreIPAddress(**kwargs)

    def get_column_type(self) -> IPAddress:
        return IPAddress()


class EmailField(CharField):
    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return Email(**kwargs)

    def get_column_type(self) -> sqlalchemy.String:
        return sqlalchemy.String(length=self.validator.max_length)  # type: ignore


class URLField(CharField):
    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        return URL(**kwargs)

    def get_column_type(self) -> sqlalchemy.String:
        return sqlalchemy.String(length=self.validator.max_length)  # type: ignore


class BinaryField(Field):
    """
    Representation of bytes/binary data.
    """

    def __init__(self, max_length: int | None = None, **kwargs: typing.Any):
        self.max_length = max_length
        super().__init__(**kwargs)

    def get_validator(self, **kwargs: typing.Any) -> SaffierField:
        kwargs["max_length"] = self.max_length
        return Binary(**kwargs)

    def get_column_type(self) -> sqlalchemy.LargeBinary:
        return sqlalchemy.LargeBinary(length=self.max_length)


class ExcludeField(Field):
    """
    Virtual field used to reserve an attribute name without creating a DB column.
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
    """
    Explicit alias for placeholders used by relation internals.
    """


class ComputedField(Field):
    """
    Virtual field whose value is resolved by getter/setter callbacks.
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
    """
    Lightweight file path/reference field stored as text.
    """

    def __init__(self, max_length: int = 255, **kwargs: typing.Any) -> None:
        kwargs.setdefault("max_length", max_length)
        super().__init__(**kwargs)


class ImageField(FileField):
    """
    Lightweight image path/reference field stored as text.
    """


class PGArrayField(Field):
    """
    PostgreSQL ARRAY field with mutable list tracking.
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
