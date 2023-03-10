import copy
import inspect
import typing
from typing import TYPE_CHECKING

import sqlalchemy

from saffier import fields as saffier_fields
from saffier.core.registry import Registry
from saffier.db.datastructures import Index
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
        "unique_together",
        "indexes",
        "foreign_key_fields",
        "parents",
        "pk",
        "one_to_one_fields",
        "pk_attribute",
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
        self._model: typing.Type["Model"] = None
        self.manager: typing.Type["Manager"] = getattr(meta, "manager", Manager())
        self.unique_together: typing.Any = getattr(meta, "unique_together", None)
        self.indexes: typing.Any = getattr(meta, "indexes", None)


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


def _check_manager_for_bases(
    base: typing.Tuple[typing.Type, ...], attrs: DictAny, meta: typing.Optional[MetaInfo] = None
) -> None:
    """
    When an abstract class is declared, we must treat the manager's value coming from the top.
    """
    if not meta:
        for key, value in inspect.getmembers(base):
            if isinstance(value, Manager) and key not in attrs:
                attrs[key] = value.__class__()
    else:
        if not meta.abstract:
            for key, value in inspect.getmembers(base):
                if isinstance(value, Manager) and key not in attrs:
                    attrs[key] = value.__class__()


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
                for key, value in inspect.getmembers(base):
                    if isinstance(value, Field) and key not in attrs:
                        attrs[key] = value

                _check_manager_for_bases(base, attrs)
            else:
                # abstract classes
                for key, value in meta.fields_mapping.items():
                    attrs[key] = value

                # For managers coming from the top that are not abstract classes
                _check_manager_for_bases(base, attrs, meta)

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
                    attrs = {"id": BigIntegerField(primary_key=True), **attrs}

                if not isinstance(attrs["id"], Field) or not attrs["id"].primary_key:
                    raise ImproperlyConfigured(
                        f"Cannot create model {name} without explicit primary key if field 'id' is already present."
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

        # Abstract classes do not allow multiple managers. This make sure it is enforced.
        if meta.abstract:
            managers = [k for k, v in attrs.items() if isinstance(v, Manager)]
            if len(managers) > 1:
                raise ImproperlyConfigured(
                    "Multiple managers are not allowed in abstract classes."
                )

            if getattr(meta, "unique_together", None) is not None:
                raise ImproperlyConfigured("unique_together cannot be in abstract classes.")

            if getattr(meta, "indexes", None) is not None:
                raise ImproperlyConfigured("indexes cannot be in abstract classes.")

        # Handle the registry of models
        if getattr(meta, "registry", None) is None:
            if hasattr(new_class, "_db_model") and new_class._db_model:
                meta.registry = _check_model_inherited_registry(bases)
            else:
                return new_class

        # Making sure the tablename is always set if the value is not provided
        if getattr(meta, "tablename", None) is None:
            tablename = f"{name.lower()}s"
            meta.tablename = tablename

        # Handle unique together
        if getattr(meta, "unique_together", None) is not None:
            unique_together = meta.unique_together
            if not isinstance(unique_together, (list, tuple)):
                value_type = type(unique_together).__name__
                raise ImproperlyConfigured(
                    f"unique_together must be a tuple or list. Got {value_type} instead."
                )
            else:
                for value in unique_together:
                    if not isinstance(value, (str, tuple)):
                        raise ValueError(
                            "The values inside the unique_together must be a string or a tuple of strings."
                        )

        # Handle indexes
        if getattr(meta, "indexes", None) is not None:
            indexes = meta.indexes
            if not isinstance(indexes, (list, tuple)):
                value_type = type(indexes).__name__
                raise ImproperlyConfigured(
                    f"indexes must be a tuple or list. Got {value_type} instead."
                )
            else:
                for value in indexes:
                    if not isinstance(value, Index):
                        raise ValueError("Meta.indexes must be a list of Index types.")

        registry = meta.registry
        new_class.database = registry.database

        # Making sure it does not generate tables if abstract it set
        if not meta.abstract:
            registry.models[name] = new_class

        for name, field in meta.fields_mapping.items():
            setattr(field, "registry", registry)
            if field.primary_key:
                new_class.pkname = name

        new_class._db_model = True
        setattr(new_class, "fields", meta.fields_mapping)

        meta._model = new_class
        meta.manager.model_class = new_class

        for key, value in attrs.items():
            if isinstance(value, Manager):
                value.model_class = new_class

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
