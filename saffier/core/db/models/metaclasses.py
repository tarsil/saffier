import copy
import inspect
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    Union,
    cast,
)

import sqlalchemy

from saffier.conf import settings
from saffier.core.connection.registry import Registry
from saffier.core.db import fields as saffier_fields
from saffier.core.db.datastructures import Index, UniqueConstraint
from saffier.core.db.fields import BigIntegerField, Field
from saffier.core.db.models.managers import Manager
from saffier.core.db.relationships.related import RelatedField
from saffier.core.db.relationships.relation import Relation
from saffier.core.signals import Broadcaster, Signal
from saffier.exceptions import ForeignKeyBadConfigured, ImproperlyConfigured

if TYPE_CHECKING:
    from saffier.core.db.models.model import Model, ReflectModel


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
        "model",
        "reflect",
        "managers",
        "is_multi",
        "multi_related",
        "related_names",
        "related_fields",
        "related_names_mapping",
        "signals",
    )

    def __init__(self, meta: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.pk: Optional[Field] = getattr(meta, "pk", None)
        self.pk_attribute: Union[Field, str] = getattr(meta, "pk_attribute", "")
        self.abstract: bool = getattr(meta, "abstract", False)
        self.fields: Set[Any] = getattr(meta, "fields", set())
        self.fields_mapping: Dict[str, Field] = getattr(meta, "fields_mapping", {})
        self.registry: Optional[Type[Registry]] = getattr(meta, "registry", None)
        self.tablename: Optional[str] = getattr(meta, "tablename", None)
        self.parents: Any = getattr(meta, "parents", [])
        self.many_to_many_fields: Set[str] = set()
        self.foreign_key_fields: Dict[str, Any] = {}
        self.model: Optional[Type["Model"]] = None
        self.manager: "Manager" = getattr(meta, "manager", Manager())
        self.unique_together: Any = getattr(meta, "unique_together", None)
        self.indexes: Any = getattr(meta, "indexes", None)
        self.reflect: bool = getattr(meta, "reflect", False)
        self.managers: List[Manager] = getattr(meta, "managers", [])
        self.is_multi: bool = getattr(meta, "is_multi", False)
        self.multi_related: Sequence[str] = getattr(meta, "multi_related", [])
        self.related_names: Set[str] = getattr(meta, "related_names", set())
        self.related_fields: Dict[str, Any] = getattr(meta, "related_fields", {})
        self.related_names_mapping: Dict[str, Any] = getattr(meta, "related_names_mapping", {})
        self.signals: Optional[Broadcaster] = getattr(meta, "signals", {})  # type: ignore


def _check_model_inherited_registry(bases: Tuple[Type, ...]) -> Type[Registry]:
    """
    When a registry is missing from the Meta class, it should look up for the bases
    and obtain the first found registry.

    If not found, then a ImproperlyConfigured exception is raised.
    """
    found_registry: Optional[Type[Registry]] = None

    for base in bases:
        meta: MetaInfo = getattr(base, "meta", None)  # type: ignore
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
    base: Tuple[Type, ...],
    attrs: Any,
    meta: Optional[MetaInfo] = None,
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
    foreign_keys: Set[Union[saffier_fields.OneToOneField, saffier_fields.ForeignKey]],
    model_class: Union["Model", "ReflectModel"],
) -> str:
    """
    Sets the related name for the foreign keys.
    When a `related_name` is generated, creates a RelatedField from the table pointed
    from the ForeignKey declaration and the the table declaring it.
    """
    for name, foreign_key in foreign_keys.items():
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
        model_class.meta.related_fields[default_related_name] = related_field

        # Set the fields mapping where a related name maps a specific foreign key
        model_class.meta.related_names_mapping[default_related_name] = name

    return cast("str", default_related_name)


def _set_many_to_many_relation(
    m2m: saffier_fields.ManyToManyField,
    model_class: Union["Model", "ReflectModel"],
    field: str,
) -> None:
    m2m.create_through_model()
    relation = Relation(through=m2m.through, to=m2m.to, owner=m2m.owner)
    setattr(model_class, settings.many_to_many_relation.format(key=field), relation)


def _register_model_signals(model_class: Type["Model"]) -> None:
    """
    Registers the signals in the model's Broadcaster and sets the defaults.
    """
    signals = Broadcaster()
    signals.pre_save = Signal()
    signals.pre_update = Signal()
    signals.pre_delete = Signal()
    signals.post_save = Signal()
    signals.post_update = Signal()
    signals.post_delete = Signal()
    model_class.meta.signals = signals


class BaseModelMeta(type):
    __slots__ = ()

    def __new__(cls, name: str, bases: Tuple[Type, ...], attrs: Any) -> Any:
        fields: Dict[str, Field] = {}
        one_to_one_fields: Any = set()
        foreign_key_fields: Any = {}
        many_to_many_fields: Any = set()
        meta_class: "Model.Meta" = attrs.get("Meta", type("Meta", (), {}))
        pk_attribute: str = "id"
        registry: Any = None

        # Searching for fields "Field" in the class hierarchy.
        def __search_for_fields(base: Type, attrs: Any) -> None:
            """
            Search for class attributes of the type fields.Field in the given class.

            If a class attribute is an instance of the Field, then it will be added to the
            field_mapping but only if the key does not exist already.

            If a primary_key field is not provided, it it automatically generate one BigIntegerField for the model.
            """

            for parent in base.__mro__[1:]:
                __search_for_fields(parent, attrs)

            meta: Union[MetaInfo, None] = getattr(base, "meta", None)
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
                    value, saffier_fields.ManyToManyField  # type: ignore
                ):
                    foreign_key_fields[key] = value
                    continue

        for slot in fields:
            attrs.pop(slot, None)
        attrs["meta"] = meta = MetaInfo(meta_class)

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
        new_class = cast("Type[Model]", model_class(cls, name, bases, attrs))

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
            meta.managers = [k for k, v in attrs.items() if isinstance(v, Manager)]

        # Handle the registry of models
        if getattr(meta, "registry", None) is None:
            if hasattr(new_class, "__db_model__") and new_class.__db_model__:
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

        new_class.__db_model__ = True
        new_class.fields = meta.fields_mapping
        meta.model = new_class
        meta.manager.model_class = new_class

        # Set the owner of the field
        for _, value in new_class.fields.items():
            value.owner = new_class

        # Sets the foreign key fields
        if meta.foreign_key_fields and not new_class.is_proxy_model:
            related_name = _set_related_name_for_foreign_keys(meta.foreign_key_fields, new_class)
            meta.related_names.add(related_name)

        for field, value in new_class.fields.items():  # type: ignore
            if isinstance(value, saffier_fields.ManyToManyField):
                _set_many_to_many_relation(value, new_class, field)

        # Set the manager
        for _, value in attrs.items():
            if isinstance(value, Manager):
                value.model_class = new_class

        # Register the signals
        _register_model_signals(new_class)

        # Update the model references with the validations of the model
        # Being done by the Edgy fields instead.
        # Generates a proxy model for each model created
        # Making sure the core model where the fields are inherited
        # And mapped contains the main proxy_model
        if not new_class.is_proxy_model and not new_class.meta.abstract:
            proxy_model = new_class.generate_proxy_model()
            new_class.__proxy_model__ = proxy_model
            new_class.__proxy_model__.parent = new_class
            meta.registry.models[new_class.__name__] = new_class  # type: ignore

        return new_class

    def get_db_shema(cls) -> Union[str, None]:
        """
        Returns a db_schema from registry if any is passed.
        """
        if hasattr(cls, "meta") and hasattr(cls.meta, "registry"):
            return cast("str", cls.meta.registry.db_schema)
        return None

    @property
    def table(cls) -> Any:
        """
        Making sure the tables on inheritance state, creates the new
        one properly.

        Making sure the following scenarios are met:

        1. If there is a context_db_schema, it will return for those, which means, the `using`
        if being utilised.
        2. If a db_schema in the `registry` is passed, then it will use that as a default.
        3. If none is passed, defaults to the shared schema of the database connected.
        """
        db_schema = cls.get_db_shema()

        if not hasattr(cls, "_table"):
            cls._table = cls.build(db_schema)
        elif hasattr(cls, "_table"):
            table = cls._table
            if table.name.lower() != cls.meta.tablename:
                cls._table = cls.build(db_schema)
        return cls._table

    @table.setter
    def table(self, value: sqlalchemy.Table) -> None:
        self._table = value

    def table_schema(cls, schema: str) -> Any:
        """
        Making sure the tables on inheritance state, creates the new
        one properly.

        The use of context vars instead of using the lru_cache comes from
        a warning from `ruff` where lru can lead to memory leaks.
        """
        return cls.build(schema=schema)

    @property
    def signals(cls) -> "Broadcaster":
        """
        Returns the signals of a class
        """
        return cast("Broadcaster", cls.meta.signals)

    @property
    def proxy_model(cls) -> Any:
        """
        Returns the proxy_model from the Model when called using the cache.
        """
        return cls.__proxy_model__

    @property
    def columns(cls) -> sqlalchemy.sql.ColumnCollection:
        return cast("sqlalchemy.sql.ColumnCollection", cls._table.columns)


class BaseModelReflectMeta(BaseModelMeta):
    def __new__(cls, name: str, bases: Tuple[Type, ...], attrs: Any) -> Any:
        new_model = super().__new__(cls, name, bases, attrs)

        registry = new_model.meta.registry

        # Remove the reflected models from the registry
        # Add the reflecte model to the views section of the refected
        if registry:
            try:
                registry.models.pop(new_model.__name__)
                registry.reflected[new_model.__name__] = new_model
            except KeyError:
                ...

        return new_model


class ModelMeta(metaclass=BaseModelMeta): ...


class ReflectMeta(metaclass=BaseModelReflectMeta): ...
