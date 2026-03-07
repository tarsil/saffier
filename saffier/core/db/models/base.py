import copy
import functools
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar, cast

import sqlalchemy
from sqlalchemy.engine import Engine
from typing_extensions import Self

import saffier
from saffier.conf import settings
from saffier.core.db.datastructures import Index, UniqueConstraint
from saffier.core.db.models.managers import Manager, RedirectManager
from saffier.core.db.models.metaclasses import (
    BaseModelMeta,
    BaseModelReflectMeta,
    MetaInfo,
    _register_model_signals,
    _set_many_to_many_relation,
    _set_related_name_for_foreign_keys,
)
from saffier.core.db.models.model_proxy import ProxyModel
from saffier.core.utils.models import DateParser, create_saffier_model, generify_model_fields
from saffier.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    from saffier import Model
    from saffier.core.signals import Broadcaster

saffier_setattr = object.__setattr__

_MODEL_COPY_EXCLUDED_ATTRS = {
    "fields",
    "meta",
    "_table",
    "_db_schemas",
    "__proxy_model__",
    "_pknames",
    "_pkcolumns",
}


class SaffierBaseModel(DateParser, metaclass=BaseModelMeta):
    """
    All the operations performed by the model added to
    a common mixin.
    """

    is_proxy_model: ClassVar[bool] = False
    query: ClassVar[Manager] = Manager()
    query_related: ClassVar[Manager] = RedirectManager(redirect_name="query")
    meta: ClassVar[MetaInfo] = MetaInfo(None)
    __db_model__: ClassVar[bool] = False
    __raw_query__: ClassVar[str | None] = None
    __proxy_model__: ClassVar[type["Model"] | None] = None
    __using_schema__: ClassVar[str | None] = None

    def __init__(self, *model_refs: Any, **kwargs: Any) -> None:
        self.setup_model_fields_from_kwargs(model_refs, kwargs)

    @staticmethod
    def _is_model_ref_instance(value: Any) -> bool:
        return (
            hasattr(value, "model_dump")
            and hasattr(value.__class__, "__model_ref_fields__")
            and hasattr(value.__class__, "__related_name__")
        )

    @classmethod
    def resolve_model_ref_field_name(cls, ref_type: type[Any]) -> str:
        for field_name, field in cls.fields.items():
            model_ref = getattr(field, "model_ref", None)
            if model_ref is not None and issubclass(ref_type, model_ref):
                return field_name
        raise saffier.ModelReferenceError(
            detail=(
                f"No RefForeignKey on '{cls.__name__}' accepts model references of type "
                f"'{ref_type.__name__}'."
            )
        )

    @classmethod
    def merge_model_refs(
        cls,
        model_refs: Sequence[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(kwargs or {})
        if not model_refs:
            return payload

        for model_ref in model_refs:
            if not cls._is_model_ref_instance(model_ref):
                raise TypeError("Positional arguments are reserved for ModelRef instances.")

            field_name = cls.resolve_model_ref_field_name(model_ref.__class__)
            existing = payload.get(field_name)
            if existing is None:
                payload[field_name] = [model_ref]
            elif isinstance(existing, Sequence) and not isinstance(
                existing, (str, bytes, bytearray)
            ):
                payload[field_name] = [*existing, model_ref]
            else:
                payload[field_name] = [existing, model_ref]
        return payload

    def setup_model_fields_from_kwargs(
        self,
        model_refs: Sequence[Any],
        kwargs: dict[str, Any],
    ) -> Any:
        """
        Loops and setup the kwargs of the model
        """
        kwargs = self.__class__.merge_model_refs(model_refs, kwargs)

        if "pk" in kwargs:
            kwargs[self.pkname] = kwargs.pop("pk")

        for key, value in kwargs.items():
            if key not in self.fields and not hasattr(self, key):
                raise ValueError(f"Invalid keyword {key} for class {self.__class__.__name__}")

            # Set model field and add to the kwargs dict
            setattr(self, key, value)
            kwargs[key] = value
        return kwargs

    async def _persist_model_references(self, field_names: set[str] | None = None) -> None:
        for field_name, field in self.fields.items():
            if not getattr(field, "is_model_reference", False):
                continue
            if field_names is not None and field_name not in field_names:
                continue
            if field_name not in self.__dict__:
                continue
            await field.persist_references(self, self.__dict__[field_name])

    @property
    def pk(self) -> Any:
        attr = getattr(self, self.pkname, None)
        if hasattr(attr, "__db_model__"):
            return getattr(attr, attr.pkname, None)  # type: ignore[union-attr]
        return attr

    @pk.setter
    def pk(self, value: Any) -> Any:
        setattr(self, self.pkname, value)

    @property
    def raw_query(self) -> Any:
        return getattr(self, self.__raw_query__)  # type: ignore

    @raw_query.setter
    def raw_query(self, value: Any) -> Any:
        setattr(self, self.raw_query, value)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self}>"

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.pkname}={self.pk})"

    @property
    def table(self) -> sqlalchemy.Table:
        if getattr(self, "_table", None) is None:
            schema = self.get_active_instance_schema()
            if schema is not None:
                return cast("sqlalchemy.Table", self.__class__.table_schema(schema))
            return cast("sqlalchemy.Table", self.__class__.table)
        return self._table

    @table.setter
    def table(self, value: sqlalchemy.Table) -> None:
        self._table = value

    @functools.cached_property
    def proxy_model(self) -> Any:
        return self.__class__.proxy_model

    @functools.cached_property
    def signals(self) -> "Broadcaster":
        return self.__class__.signals  # type: ignore

    @functools.cached_property
    def identifying_db_fields(self) -> Sequence[str]:
        """
        Returns the database columns that uniquely identify the current instance.

        Saffier currently uses the model primary key columns for this.
        """
        pkcolumns = getattr(self.__class__, "pkcolumns", ())
        return tuple(pkcolumns) or (self.pkname,)

    @property
    def can_load(self) -> bool:
        """
        Indicates whether this instance has enough identifying data to be reloaded.
        """
        return bool(
            self.meta.registry
            and not self.meta.abstract
            and all(
                getattr(self, field_name, None) is not None
                for field_name in self.identifying_db_fields
            )
        )

    def create_model_key(self) -> tuple[Any, ...]:
        """
        Creates a stable key for recursion guards while walking model graphs.
        """
        return (
            self.__class__,
            *(getattr(self, field_name, None) for field_name in self.identifying_db_fields),
        )

    def _has_loaded_db_fields(self) -> bool:
        return all(
            field_name in self.__dict__
            for field_name, field in self.fields.items()
            if field.has_column()
        )

    @classmethod
    def get_active_class_schema(cls) -> str | None:
        return cast("str | None", getattr(cls, "__using_schema__", None))

    def get_active_instance_schema(self) -> str | None:
        explicit = self.__dict__.get("__using_schema__", None)
        if explicit is not None:
            return cast("str | None", explicit)
        table = self.__dict__.get("_table", None)
        if table is not None:
            return cast("str | None", getattr(table, "schema", None))
        return self.__class__.get_active_class_schema()

    async def load_recursive(
        self,
        only_needed: bool = False,
        only_needed_nest: bool = False,
        _seen: set[tuple[Any, ...]] | None = None,
    ) -> None:
        """
        Recursively loads this instance and its foreign-key relations.
        """
        model_key = self.create_model_key()
        if _seen is None:
            _seen = {model_key}
        elif model_key in _seen:
            return
        else:
            _seen.add(model_key)

        was_loaded = self._has_loaded_db_fields()
        if self.can_load:
            await self.load(only_needed=only_needed)

        if only_needed_nest and was_loaded:
            return

        for field_name in self.meta.foreign_key_fields:
            value = getattr(self, field_name, None)
            if value is not None and hasattr(value, "load_recursive"):
                await value.load_recursive(
                    only_needed=only_needed,
                    only_needed_nest=True,
                    _seen=_seen,
                )

    def get_instance_name(self) -> str:
        """
        Returns the name of the class in lowercase.
        """
        return self.__class__.__name__.lower()

    @classmethod
    def _copy_model_definitions(
        cls,
        *,
        registry: "saffier.Registry | None" = None,
        unlink_same_registry: bool = True,
    ) -> dict[str, Any]:
        from saffier.core.db.fields.base import ForeignKey, ManyToManyField

        definitions: dict[str, Any] = {}
        source_registry = getattr(cls.meta, "registry", None)

        for field_name, field in cls.fields.items():
            if getattr(field, "no_copy", False):
                continue
            field_copy = copy.copy(field)
            if hasattr(field_copy, "_target"):
                delattr(field_copy, "_target")

            if source_registry not in (None, False):
                if isinstance(field_copy, ForeignKey):
                    target = field.target
                    if getattr(target.meta, "registry", None) is source_registry:
                        if unlink_same_registry:
                            field_copy.to = target.__name__
                        elif registry is not None:
                            field_copy.related_name = False
                elif isinstance(field_copy, ManyToManyField):
                    target = field.target
                    if getattr(target.meta, "registry", None) is source_registry and unlink_same_registry:
                        field_copy.to = target.__name__
                    through = getattr(field_copy, "through", None)
                    if isinstance(through, type) and getattr(through.meta, "registry", None) is source_registry:
                        if unlink_same_registry:
                            field_copy.through = through.__name__

            definitions[field_name] = field_copy

        for manager_name in getattr(cls.meta, "managers", []):
            manager = getattr(cls, manager_name, None)
            if isinstance(manager, Manager):
                definitions[manager_name] = copy.copy(manager)

        return definitions

    @classmethod
    def copy_saffier_model(
        cls,
        registry: "saffier.Registry | None" = None,
        name: str = "",
        unlink_same_registry: bool = True,
        on_conflict: str = "error",
    ) -> type["Model"]:
        definitions = {
            key: value
            for key, value in cls.__dict__.items()
            if key not in _MODEL_COPY_EXCLUDED_ATTRS and not key.startswith("__")
        }
        definitions.update(
            cls._copy_model_definitions(registry=registry, unlink_same_registry=unlink_same_registry)
        )
        definitions["__skip_registry__"] = True

        meta = type(
            "Meta",
            (),
            {
                "registry": False,
                "tablename": getattr(cls.meta, "tablename", None),
                "table_prefix": getattr(cls.meta, "table_prefix", None),
                "unique_together": list(getattr(cls.meta, "unique_together", []) or []),
                "indexes": list(getattr(cls.meta, "indexes", []) or []),
                "constraints": list(getattr(cls.meta, "constraints", []) or []),
                "reflect": getattr(cls.meta, "reflect", False),
                "abstract": getattr(cls.meta, "abstract", False),
                "is_tenant": getattr(cls.meta, "is_tenant", None),
                "register_default": getattr(cls.meta, "register_default", None),
            },
        )

        copied_model = create_saffier_model(
            name or cls.__name__,
            cls.__module__,
            __definitions__=definitions,
            __metadata__=meta,
            __qualname__=cls.__qualname__,
            __bases__=cls.__bases__,
        )
        copied_model.database = getattr(cls, "database", None)
        copied_model.__using_schema__ = getattr(cls, "__using_schema__", None)

        if registry is None:
            copied_model.meta.registry = False
            return copied_model
        return copied_model.add_to_registry(registry, on_conflict=on_conflict)

    copy_model = copy_saffier_model
    copy_edgy_model = copy_saffier_model

    @classmethod
    def real_add_to_registry(
        cls,
        *,
        registry: "saffier.Registry",
        name: str = "",
        database: bool | Any | str = "keep",
        on_conflict: str = "error",
    ) -> type["Model"]:
        if getattr(cls.meta, "registry", None) not in (None, False, registry):
            return cls.copy_saffier_model(
                registry=registry,
                name=name or cls.__name__,
                on_conflict=on_conflict,
            )

        model_name = name or cls.__name__
        if model_name in registry.models:
            if on_conflict == "keep":
                return cast("type[Model]", registry.models[model_name])
            if on_conflict == "replace":
                registry.delete_model(model_name)
            else:
                raise ImproperlyConfigured(
                    f'A model with the same name is already registered: "{model_name}".'
                )

        cls.meta.registry = registry
        cls.__name__ = model_name

        if database is True:
            cls.database = registry.database
        elif database not in (False, "keep"):
            cls.database = database
        elif getattr(cls, "database", None) is None:
            cls.database = registry.database

        registry.models[model_name] = cls
        cls.__db_model__ = True
        cls.meta.model = cls
        cls.fields = cls.meta.fields
        cls._table = None
        cls._db_schemas = {}

        for field_name, field in cls.fields.items():
            field.owner = cls
            field.registry = registry
            if field.primary_key:
                cls.pkname = field_name

        for manager_name in getattr(cls.meta, "managers", []):
            manager = getattr(cls, manager_name, None)
            if isinstance(manager, Manager):
                manager.name = manager_name
                manager.model_class = cls

        if getattr(cls.meta, "foreign_key_fields", None) and not cls.is_proxy_model:
            related_names = _set_related_name_for_foreign_keys(cls.meta.foreign_key_fields, cls)
            cls.meta.related_names.update(related_names)

        for field_name, field in list(cls.fields.items()):
            if isinstance(field, saffier.ManyToManyField):
                _set_many_to_many_relation(field, cls, field_name)

        _register_model_signals(cls)
        cls.__proxy_model__ = None
        if not cls.is_proxy_model and not cls.meta.abstract:
            proxy_model = cls.generate_proxy_model()
            cls.__proxy_model__ = proxy_model
            cls.__proxy_model__.parent = cls
            registry.models[model_name] = cls

        if hasattr(registry, "_handle_model_registration"):
            registry._handle_model_registration(cls)
        registry.execute_model_callbacks(cls)
        return cast("type[Model]", cls)

    @classmethod
    def add_to_registry(
        cls,
        registry: "saffier.Registry",
        name: str = "",
        database: bool | Any | str = "keep",
        *,
        on_conflict: str = "error",
    ) -> type["Model"]:
        return cls.real_add_to_registry(
            registry=registry,
            name=name,
            database=database,
            on_conflict=on_conflict,
        )

    @classmethod
    def generate_proxy_model(cls) -> type["Model"]:
        """
        Generates a proxy model for each model. This proxy model is a simple
        shallow copy of the original model being generated.
        """
        existing_proxy = cls.__dict__.get("__proxy_model__")
        if existing_proxy:
            return existing_proxy

        fields = {key: copy.copy(field) for key, field in cls.fields.items()}
        proxy_model = ProxyModel(
            name=cls.__name__,
            module=cls.__module__,
            metadata=cls.meta,
            definitions=fields,
        )

        proxy_model.build()
        generify_model_fields(proxy_model.model)
        return proxy_model.model

    @classmethod
    def build(cls, schema: str | None = None) -> sqlalchemy.Table:
        """
        Performs the operation of building the core SQLAlchemy Table object.
        Builds the constrainst, indexes, columns and metadata based on the
        provided Meta class object.
        """
        tablename = cls.meta.tablename
        registry = cls.meta.registry
        database = getattr(cls, "database", None)
        if database is not None and hasattr(registry, "metadata_by_url"):
            registry_metadata = cast(
                "sqlalchemy.MetaData", registry.metadata_by_url[str(database.url)]
            )
        else:
            registry_metadata = cast("sqlalchemy.MetaData", registry._metadata)  # type: ignore
        schema_metadata_cache: dict[str | None, sqlalchemy.MetaData] = getattr(
            registry,
            "_schema_metadata_cache",
            {},
        )
        if not hasattr(registry, "_schema_metadata_cache"):
            registry._schema_metadata_cache = schema_metadata_cache
        registry_schema = registry.db_schema

        # Keep tenant/using table generation isolated from the shared registry
        # metadata. This prevents cross-schema table/index leakage in metadata.
        if schema == registry_schema:
            metadata = registry_metadata
            metadata.schema = schema
        else:
            if schema not in schema_metadata_cache:
                schema_metadata_cache[schema] = sqlalchemy.MetaData(schema=schema)
            metadata = schema_metadata_cache[schema]

        table_key = tablename if schema is None else f"{schema}.{tablename}"
        existing_table = metadata.tables.get(table_key)
        if existing_table is not None:
            return existing_table

        unique_together = cls.meta.unique_together
        index_constraints = cls.meta.indexes
        table_constraints = cls.meta.constraints

        columns = []
        for name, field in cls.fields.items():
            if field.has_column():
                columns.append(field.get_column(name))

        # Handle the uniqueness together
        uniques = []
        for field in unique_together or []:
            unique_constraint = cls._get_unique_constraints(field)
            uniques.append(unique_constraint)

        # Handle the indexes
        indexes = []
        for field in index_constraints or []:
            index = cls._get_indexes(field)
            indexes.append(index)

        constraints = []
        for constraint in table_constraints or []:
            constraints.append(constraint)

        return sqlalchemy.Table(
            tablename,
            metadata,
            *columns,
            *uniques,
            *indexes,
            *constraints,
            extend_existing=True,  # type: ignore
        )

    @classmethod
    def _get_unique_constraints(cls, columns: Sequence) -> sqlalchemy.UniqueConstraint | None:
        """
        Returns the unique constraints for the model.

        The columns must be a a list, tuple of strings or a UniqueConstraint object.
        """
        if isinstance(columns, str):
            return sqlalchemy.UniqueConstraint(columns)
        elif isinstance(columns, UniqueConstraint):
            return sqlalchemy.UniqueConstraint(*columns.fields)
        return sqlalchemy.UniqueConstraint(*columns)

    @classmethod
    def _get_indexes(cls, index: Index) -> sqlalchemy.Index | None:
        """
        Creates the index based on the Index fields
        """
        return sqlalchemy.Index(index.name, *index.fields)  # type: ignore

    def update_from_dict(self, dict_values: dict[str, Any]) -> Self:
        """Updates the current model object with the new fields"""
        for key, value in dict_values.items():
            setattr(self, key, value)
        return self

    def extract_db_fields(self) -> dict[str, Any]:
        """
        Extacts all the db fields and excludes the related_names since those
        are simply relations.
        """
        related_names = self.meta.related_names
        return {
            k: v
            for k, v in self.__dict__.items()
            if k not in related_names and k in self.fields and self.fields[k].has_column()
        }

    def __setattr__(self, key: Any, value: Any) -> Any:
        if key == "__using_schema__":
            self.__dict__.pop("_table", None)
        if key in self.fields:
            # Setting a relationship to a raw pk value should set a
            # fully-fledged relationship instance, with just the pk loaded.
            field = self.fields[key]
            if getattr(field, "is_computed", False):
                field.set_value(self, key, value)
                return
            if isinstance(field, saffier.ManyToManyField):
                value = getattr(self, settings.many_to_many_relation.format(key=key))
                super().__setattr__(key, value)
                return
            if field.is_virtual:
                if hasattr(field, "set_value") and not isinstance(field, saffier.ManyToManyField):
                    field.set_value(self, key, value)
                    return
                super().__setattr__(key, value)
                return
            value = self.fields[key].expand_relationship(value)
        super().__setattr__(key, value)

    def __get_instance_values(self, instance: Any) -> set[tuple[str, Any]]:
        values: set[tuple[str, Any]] = set()
        for key, value in instance.__dict__.items():
            if key not in instance.fields or value is None:
                continue
            if hasattr(value, "pk"):
                value = value.pk
            try:
                hash(value)
            except TypeError:
                value = repr(value)
            values.add((key, value))
        return values

    def __eq__(self, other: Any) -> bool:
        if self.__class__ != other.__class__:
            return False
        original = self.__get_instance_values(instance=self)
        other_values = self.__get_instance_values(instance=other)
        return original == other_values


class SaffierBaseReflectModel(SaffierBaseModel, metaclass=BaseModelReflectMeta):
    """
    Reflect on async engines is not yet supported, therefore, we need to make a sync_engine
    call.
    """

    @classmethod
    @functools.lru_cache
    def get_engine(cls, url: str) -> Engine:
        return sqlalchemy.create_engine(url)

    @property
    def pk(self) -> Any:
        return getattr(self, self.pkname, None)

    @pk.setter
    def pk(self, value: Any) -> Any:
        setattr(self, self.pkname, value)

    @classmethod
    def build(cls, schema: str | None = None) -> sqlalchemy.Table:
        """
        The inspect is done in an async manner and reflects the objects from the database.
        """
        registry = cls.meta.registry
        database = getattr(cls, "database", None)
        if database is not None and hasattr(registry, "metadata_by_url"):
            registry_metadata = cast(
                "sqlalchemy.MetaData", registry.metadata_by_url[str(database.url)]
            )
        else:
            registry_metadata = cast("sqlalchemy.MetaData", registry._metadata)  # type: ignore
        schema_metadata_cache: dict[str | None, sqlalchemy.MetaData] = getattr(
            registry,
            "_schema_metadata_cache",
            {},
        )
        if not hasattr(registry, "_schema_metadata_cache"):
            registry._schema_metadata_cache = schema_metadata_cache
        registry_schema = registry.db_schema

        if schema == registry_schema:
            metadata = registry_metadata
            metadata.schema = schema
        else:
            if schema not in schema_metadata_cache:
                schema_metadata_cache[schema] = sqlalchemy.MetaData(schema=schema)
            metadata = schema_metadata_cache[schema]
        tablename: str = cast("str", cls.meta.tablename)
        table_key = tablename if schema is None else f"{schema}.{tablename}"
        existing_table = metadata.tables.get(table_key)
        if existing_table is not None:
            return existing_table
        return cls.reflect(tablename, metadata)

    @classmethod
    def reflect(cls, tablename: str, metadata: sqlalchemy.MetaData) -> sqlalchemy.Table:
        try:
            database = getattr(cls, "database", None)
            autoload_with = (
                database.sync_engine
                if database is not None and getattr(database, "sync_engine", None) is not None
                else cls.meta.registry.sync_engine  # type: ignore[union-attr]
            )
            return sqlalchemy.Table(
                tablename,
                metadata,
                schema=metadata.schema,
                autoload_with=autoload_with,
            )
        except Exception as e:
            raise ImproperlyConfigured(
                detail=f"Table with the name {tablename} does not exist."
            ) from e
