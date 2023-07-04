import copy
import inspect
import typing
from typing import TYPE_CHECKING, Any

import sqlalchemy

from saffier.conf import settings
from saffier.core.registry import Registry
from saffier.db.datastructures import Index, UniqueConstraint
from saffier.db.models import fields as saffier_fields
from saffier.db.models.fields import BigIntegerField, Field
from saffier.db.models.manager import Manager
from saffier.db.relationships.related import RelatedField
from saffier.db.relationships.relation import Relation
from saffier.exceptions import ForeignKeyBadConfigured, ImproperlyConfigured

if TYPE_CHECKING:
    from saffier.db.models.base import Model, ReflectModel


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
        "many_to_many_fields",
        "pk_attribute",
        "manager",
        "_model",
        "reflect",
        "_managers",
        "is_multi",
        "multi_related",
        "related_names",
    )

    def __init__(self, meta: typing.Optional["Model.Meta"] = None) -> None:
        self.abstract: bool = getattr(meta, "abstract", False)
        self.fields: typing.Set = set()
        self.fields_mapping: typing.Dict[str, Field] = {}
        self.registry: typing.Optional[typing.Type[Registry]] = getattr(meta, "registry", None)
        self.tablename: typing.Optional[str] = getattr(meta, "tablename", None)
        self.parents: typing.Any = getattr(meta, "parents", None) or []
        self.pk: typing.Optional[Field] = None
        self.one_to_one_fields: typing.Set[str] = set()
        self.many_to_many_fields: typing.Set[str] = set()
        self.foreign_key_fields: typing.Set[str] = set()
        self.pk_attribute: typing.Union[Field, str] = getattr(meta, "pk_attribute", "")
        self._model: typing.Optional[typing.Type["Model"]] = None
        self.manager: Manager = getattr(meta, "manager", Manager())
        self.unique_together: typing.Any = getattr(meta, "unique_together", None)
        self.indexes: typing.Any = getattr(meta, "indexes", None)
        self.reflect: bool = getattr(meta, "reflect", False)
        self._managers: bool = getattr(meta, "_managers", None)
        self.is_multi: bool = getattr(meta, "is_multi", False)
        self.multi_related: typing.List[str] = getattr(meta, "multi_related", [])
        self.related_names: typing.Set[str] = set()


def _check_model_inherited_registry(
    bases: typing.Tuple[typing.Type, ...]
) -> typing.Type[Registry]:
    """
    When a registry is missing from the Meta class, it should look up for the bases
    and obtain the first found registry.

    If not found, then a ImproperlyConfigured exception is raised.
    """
    found_registry: typing.Optional[typing.Type[Registry]] = None

    for base in bases:
        meta: MetaInfo = getattr(base, "_meta", None)  # type: ignore
        if not meta:
            continue

        if getattr(meta, "registry", None) is not None:
            found_registry = meta.registry
            break

    if not found_registry:
        raise ImproperlyConfigured(
            "Registry for the table not found in the Meta class or any of the superclasses. You must set thr registry in the Meta."
        )
    return found_registry


def _check_manager_for_bases(
    base: typing.Tuple[typing.Type, ...],
    attrs: typing.Any,
    meta: typing.Optional[MetaInfo] = None,
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


def _set_related_name_for_foreign_keys(
    foreign_keys: typing.Set[
        typing.Union[saffier_fields.OneToOneField, saffier_fields.ForeignKey]
    ],
    model_class: typing.Union["Model", "ReflectModel"],
) -> str:
    """
    Sets the related name for the foreign keys.
    When a `related_name` is generated, creates a RelatedField from the table pointed
    from the ForeignKey declaration and the the table declaring it.
    """
    for foreign_key in foreign_keys:
        default_related_name = getattr(foreign_key, "related_name", None)

        if not default_related_name:
            default_related_name = f"{model_class.__name__.lower()}s_set"

        elif hasattr(foreign_key.target, default_related_name):
            raise ForeignKeyBadConfigured(
                f"Multiple related_name with the same value '{default_related_name}' found to the same target. Related names must be different."
            )

        foreign_key.related_name = default_related_name

        related_field = RelatedField(
            related_name=default_related_name,
            related_to=foreign_key.target,
            related_from=model_class,
        )

        # Set the related name
        setattr(foreign_key.target, default_related_name, related_field)

    return default_related_name


def _set_many_to_many_relation(
    m2m: saffier_fields.ManyToManyField,
    model_class: typing.Union["Model", "ReflectModel"],
    field: str,
) -> None:
    m2m.create_through_model()
    relation = Relation(through=m2m.through, to=m2m.to, owner=m2m.owner)
    setattr(model_class, settings.many_to_many_relation.format(key=field), relation)


class BaseModelMeta(type):
    __slots__ = ()

    def __new__(cls, name: str, bases: typing.Tuple[typing.Type, ...], attrs: Any) -> typing.Any:
        fields: typing.Dict[str, Field] = {}
        one_to_one_fields: typing.Any = set()
        foreign_key_fields: typing.Any = set()
        many_to_many_fields: typing.Any = set()
        meta_class: "Model.Meta" = attrs.get("Meta", type("Meta", (), {}))
        pk_attribute: str = "id"
        registry: typing.Any = None

        # Searching for fields "Field" in the class hierarchy.
        def __search_for_fields(base: typing.Type, attrs: Any) -> None:
            """
            Search for class attributes of the type fields.Field in the given class.

            If a class attribute is an instance of the Field, then it will be added to the
            field_mapping but only if the key does not exist already.

            If a primary_key field is not provided, it it automatically generate one BigIntegerField for the model.
            """

            for parent in base.__mro__[1:]:
                __search_for_fields(parent, attrs)

            meta: typing.Union[MetaInfo, None] = getattr(base, "_meta", None)
            if not meta:
                # Mixins and other classes
                for key, value in inspect.getmembers(base):
                    if isinstance(value, Field) and key not in attrs:
                        attrs[key] = value

                _check_manager_for_bases(base, attrs)  # type: ignore
            else:
                # abstract classes
                for key, value in meta.fields_mapping.items():
                    attrs[key] = value

                # For managers coming from the top that are not abstract classes
                _check_manager_for_bases(base, attrs, meta)  # type: ignore

        # Search in the base classes
        inherited_fields: Any = {}
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
                    attrs = {"id": BigIntegerField(primary_key=True, autoincrement=True), **attrs}

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
                    continue
                elif isinstance(value, saffier_fields.ManyToManyField):
                    many_to_many_fields.add(value)
                    continue
                elif isinstance(value, saffier_fields.ForeignKey) and not isinstance(
                    value, saffier_fields.ManyToManyField
                ):
                    foreign_key_fields.add(value)
                    continue

        for slot in fields:
            attrs.pop(slot, None)
        attrs["_meta"] = meta = MetaInfo(meta_class)

        meta.fields_mapping = fields
        meta.foreign_key_fields = foreign_key_fields
        meta.one_to_one_fields = one_to_one_fields
        meta.many_to_many_fields = many_to_many_fields
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
        else:
            meta._managers = [k for k, v in attrs.items() if isinstance(v, Manager)]

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
                    if not isinstance(value, (str, tuple, UniqueConstraint)):
                        raise ValueError(
                            "The values inside the unique_together must be a string, a tuple of strings or an instance of UniqueConstraint."
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
            field.registry = registry
            if field.primary_key:
                new_class.pkname = name

        new_class._db_model = True
        new_class.fields = meta.fields_mapping

        meta._model = new_class  # type: ignore
        meta.manager.model_class = new_class

        # Set the owner of the field
        for _, value in new_class.fields.items():
            value.owner = new_class

        # Sets the foreign key fields
        if meta.foreign_key_fields:
            related_name = _set_related_name_for_foreign_keys(meta.foreign_key_fields, new_class)
            meta.related_names.add(related_name)

        for field, value in new_class.fields.items():
            if isinstance(value, saffier_fields.ManyToManyField):
                _set_many_to_many_relation(value, new_class, field)

        # Set the manager
        for _, value in attrs.items():
            if isinstance(value, Manager):
                value.model_class = new_class

        return new_class

    @property
    def table(cls) -> typing.Any:
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


class BaseModelReflectMeta(BaseModelMeta):
    def __new__(cls, name: str, bases: typing.Tuple[typing.Type, ...], attrs: Any) -> typing.Any:
        new_model = super().__new__(cls, name, bases, attrs)

        registry = new_model._meta.registry

        # Remove the reflected models from the registry
        # Add the reflecte model to the views section of the refected
        if registry:
            try:
                registry.models.pop(new_model.__name__)
                registry.reflected[new_model.__name__] = new_model
            except KeyError:
                ...

        return new_model


class ModelMeta(metaclass=BaseModelMeta):
    ...


class ReflectMeta(metaclass=BaseModelReflectMeta):
    ...
