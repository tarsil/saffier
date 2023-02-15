import copy
import inspect
import typing
from typing import TYPE_CHECKING

import sqlalchemy

from saffier import fields as saffier_fields
from saffier.core.registry import Registry
from saffier.db.manager import Manager
from saffier.exceptions import ImproperlyConfigured
from saffier.fields import BigIntegerField, Field
from saffier.types import DictAny

if TYPE_CHECKING:
    from saffier.models import Model


class MetaInfo:
    __slots__ = (
        "abstract",
        "fields",
        "fields_mapping",
        "registry",
        "tablename",
        "indexes",
        "unique_together",
        "foreign_key_fields",
        "parents",
        "pk",
        "one_to_one_fields",
        "pk_attribute",
        "is_inherited",
        "is_model",
        "manager",
        "_model",
    )

    def __init__(self, meta: "Model.Meta") -> None:
        self.abstract: bool = getattr(meta, "abstract", False)
        self.fields: typing.Set = set()
        self.fields_mapping: typing.Dict[str, Field] = {}
        self.registry: typing.Optional[typing.Type[Registry]] = getattr(meta, "registry", None)
        self.tablename: typing.Optional[str] = getattr(meta, "tablename", None)
        self.parents: typing.Any = getattr(meta, "parents", None) or []
        self.pk: Field = None
        self.one_to_one_fields: typing.Set[str] = set()
        self.foreign_key_fields: typing.Set[str] = set()
        self.pk_attribute: Field = getattr(meta, "pk_attribute", "")
        self.is_inherited: bool = getattr(meta, "is_inherited", False)
        self.is_model: bool = False
        self._model: typing.Type["Model"] = None
        self.manager = getattr(meta, "manager", Manager())


def _check_model_inherited_registry(bases: typing.Tuple[typing.Type, ...]) -> Registry:
    """
    When a registry is missing from the Meta class, it should look up for the bases
    and obtain the first found registry.

    If not found, then a ImproperlyConfigured exception is raised.
    """
    found_registry: Registry = None

    for base in bases:
        meta: MetaInfo = getattr(base, "_meta", None)
        if not meta:
            continue

        if getattr(meta, "registry", None) is not None:
            found_registry = getattr(meta, "registry")
            break

    if not found_registry:
        raise ImproperlyConfigured(
            "Registry for the table not found in the Meta class or any of the superclasses. You must set thr registry in the Meta."
        )
    return found_registry


class BaseModelMeta(type):
    __slots__ = ()

    def __new__(cls, name: str, bases: typing.Tuple[typing.Type, ...], attrs: DictAny):
        fields: typing.Dict[str, Field] = {}
        one_to_one_fields: typing.Set[str] = set()
        foreign_key_fields: typing.Set[str] = set()
        meta_class: "Model.Meta" = attrs.get("Meta", type("Meta", (), {}))
        pk_attribute: str = "id"
        registry: typing.Any = None

        # Searching for fields "Field" in the class hierarchy.
        def __search_for_fields(base: typing.Type, attrs: DictAny) -> None:
            """
            Search for class attributes of the type fields.Field in the given class.

            If a class attribute is an instance of the Field, then it will be added to the
            field_mapping but only if the key does not exist already.

            If a primary_key field is not provided, it it automatically generate one BigIntegerField for the model.
            """

            for parent in base.__mro__[1:]:
                __search_for_fields(parent, attrs)

            meta: MetaInfo = getattr(base, "_meta", None)
            if not meta:
                # Mixins and other classes
                for key, value in base.__dict__.items():
                    if isinstance(value, Field) and key not in attrs:
                        attrs[key] = value

                for key, value in inspect.getmembers(base):
                    if isinstance(value, Manager) and key not in attrs:
                        attrs[key] = value.__class__()
            else:
                # abstract classes
                for key, value in meta.fields_mapping.items():
                    attrs[key] = value

        # Search in the base classes
        inherited_fields: DictAny = {}
        for base in bases:
            __search_for_fields(base, inherited_fields)

        if inherited_fields:
            # Making sure the inherited fields are before the new defined.
            attrs = {**inherited_fields, **attrs}

        # Handle with multiple primary keys and auto generated field if no primary key is provided
        if name != "Model":
            is_pk_present = False
            for key, value in attrs.items():
                if isinstance(value, Field):
                    if value.primary_key:
                        if is_pk_present:
                            raise ImproperlyConfigured(
                                f"Cannot create model {name} with multiple primary keys."
                            )
                        is_pk_present = True
                        pk_attribute = key

            if not is_pk_present and not getattr(meta_class, "abstract", None):
                if "id" not in attrs:
                    attrs = {"id": BigIntegerField(primary_key=True, **attrs)}

                if not isinstance(attrs["id"], Field) or not attrs["id"].primary_key:
                    raise ImproperlyConfigured(
                        f"Cannot create model {name} without explicit primary key if field 'id' is already present"
                    )

        for key, value in attrs.items():
            if isinstance(value, Field):
                if getattr(meta_class, "abstract", None):
                    value = copy.copy(value)

                fields[key] = value

                if isinstance(value, saffier_fields.OneToOneField):
                    one_to_one_fields.add(value)
                elif isinstance(value, saffier_fields.ForeignKey):
                    foreign_key_fields.add(value)

        for slot in fields:
            attrs.pop(slot, None)
        attrs["_meta"] = meta = MetaInfo(meta_class)

        meta.fields_mapping = fields
        meta.foreign_key_fields = foreign_key_fields
        meta.one_to_one_fields = one_to_one_fields
        meta.pk_attribute = pk_attribute
        meta.pk = fields.get(pk_attribute)

        if not fields:
            meta.abstract = True

        model_class = super().__new__

        # Ensure the initialization is only performed for subclasses of Model
        parents = [parent for parent in bases if isinstance(parent, BaseModelMeta)]
        if not parents:
            return model_class(cls, name, bases, attrs)

        meta.parents = parents
        new_class = model_class(cls, name, bases, attrs)

        if getattr(meta, "registry", None) is None:
            if hasattr(new_class, "_db_model") and new_class._db_model:
                meta.registry = _check_model_inherited_registry(bases)
            else:
                return new_class

        # Making sure the tablename is always set if the value is not provided
        if getattr(meta, "tablename", None) is None:
            tablename = f"{name.lower()}s"
            meta.tablename = tablename

        registry = meta.registry
        new_class.database = registry.database

        # Making sure it does not generate tables if abstract it set
        if not meta.abstract:
            registry.models[name] = new_class

        for name, field in meta.fields_mapping.items():
            setattr(field, "registry", registry)
            if field.primary_key:
                new_class.pkname = name

        # for key, value in inspect.getmembers(new_class):
        #     if isinstance(value, Manager):
        #         value.model_class = new_class

        meta._model = new_class
        meta.manager.model_class = new_class

        new_class._db_model = True
        setattr(new_class, "fields", meta.fields_mapping)
        return new_class

    @property
    def table(cls):
        """
        Making sure the tables on inheritance state, creates the new
        one properly.
        """
        if not hasattr(cls, "_table"):
            cls._table = cls.build_table()
        elif hasattr(cls, "_table"):
            table = cls._table
            if table.name.lower() != cls._meta.tablename:
                cls._table = cls.build_table()
        return cls._table

    @property
    def columns(cls) -> sqlalchemy.sql.ColumnCollection:
        return cls._table.columns


class ModelMeta(metaclass=BaseModelMeta):
    ...