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
from saffier.core.db.models.metaclasses import BaseModelMeta, BaseModelReflectMeta, MetaInfo
from saffier.core.db.models.model_proxy import ProxyModel
from saffier.core.utils.models import DateParser, generify_model_fields
from saffier.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    from saffier import Model
    from saffier.core.signals import Broadcaster

saffier_setattr = object.__setattr__


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

    def __init__(self, **kwargs: Any) -> None:
        self.setup_model_fields_from_kwargs(kwargs)

    def setup_model_fields_from_kwargs(self, kwargs: Any) -> Any:
        """
        Loops and setup the kwargs of the model
        """
        if "pk" in kwargs:
            kwargs[self.pkname] = kwargs.pop("pk")

        for key, value in kwargs.items():
            if key not in self.fields and not hasattr(self, key):
                raise ValueError(f"Invalid keyword {key} for class {self.__class__.__name__}")

            # Set model field and add to the kwargs dict
            setattr(self, key, value)
            kwargs[key] = value
        return kwargs

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

    def get_instance_name(self) -> str:
        """
        Returns the name of the class in lowercase.
        """
        return self.__class__.__name__.lower()

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
        registry_metadata: sqlalchemy.MetaData = cast(
            "sqlalchemy.MetaData", cls.meta.registry._metadata
        )  # type: ignore
        schema_metadata_cache: dict[str | None, sqlalchemy.MetaData] = getattr(
            cls.meta.registry,
            "_schema_metadata_cache",
            {},
        )
        if not hasattr(cls.meta.registry, "_schema_metadata_cache"):
            cls.meta.registry._schema_metadata_cache = schema_metadata_cache
        registry_schema = cls.meta.registry.db_schema

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
        registry_metadata = cast("sqlalchemy.MetaData", cls.meta.registry._metadata)  # type: ignore
        schema_metadata_cache: dict[str | None, sqlalchemy.MetaData] = getattr(
            cls.meta.registry,
            "_schema_metadata_cache",
            {},
        )
        if not hasattr(cls.meta.registry, "_schema_metadata_cache"):
            cls.meta.registry._schema_metadata_cache = schema_metadata_cache
        registry_schema = cls.meta.registry.db_schema

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
                autoload_with=autoload_with,
            )
        except Exception as e:
            raise ImproperlyConfigured(
                detail=f"Table with the name {tablename} does not exist."
            ) from e
