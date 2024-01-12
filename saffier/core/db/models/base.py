import copy
import functools
from typing import TYPE_CHECKING, Any, ClassVar, Dict, Optional, Sequence, Set, Type, Union, cast

import sqlalchemy
from sqlalchemy.engine import Engine
from typing_extensions import Self

import saffier
from saffier.conf import settings
from saffier.core.db.datastructures import Index, UniqueConstraint
from saffier.core.db.models.managers import Manager
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
    meta: ClassVar[MetaInfo] = MetaInfo(None)
    __db_model__: ClassVar[bool] = False
    __raw_query__: ClassVar[Optional[str]] = None
    __proxy_model__: ClassVar[Union[Type["Model"], None]] = None

    def __init__(self, **kwargs: Any) -> None:
        self.setup_model_fields_from_kwargs(kwargs)

    def setup_model_fields_from_kwargs(self, kwargs: Any) -> Any:
        """
        Loops and setup the kwargs of the model
        """
        if "pk" in kwargs:
            kwargs[self.pkname] = kwargs.pop("pk")

        for key, value in kwargs.items():
            if key not in self.fields:
                if not hasattr(self, key):
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
    def generate_proxy_model(cls) -> Type["Model"]:
        """
        Generates a proxy model for each model. This proxy model is a simple
        shallow copy of the original model being generated.
        """
        if cls.__proxy_model__:
            return cls.__proxy_model__

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
    def build(cls, schema: Optional[str] = None) -> sqlalchemy.Table:
        """
        Performs the operation of building the core SQLAlchemy Table object.
        Builds the constrainst, indexes, columns and metadata based on the
        provided Meta class object.
        """
        tablename = cls.meta.tablename
        metadata: sqlalchemy.MetaData = cast("sqlalchemy.MetaData", cls.meta.registry._metadata)  # type: ignore
        metadata.schema = schema

        unique_together = cls.meta.unique_together
        index_constraints = cls.meta.indexes

        columns = []
        for name, field in cls.fields.items():
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

        return sqlalchemy.Table(
            tablename, metadata, *columns, *uniques, *indexes, extend_existing=True  # type: ignore
        )

    @classmethod
    def _get_unique_constraints(cls, columns: Sequence) -> Optional[sqlalchemy.UniqueConstraint]:
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
    def _get_indexes(cls, index: Index) -> Optional[sqlalchemy.Index]:
        """
        Creates the index based on the Index fields
        """
        return sqlalchemy.Index(index.name, *index.fields)  # type: ignore

    def update_from_dict(self, dict_values: Dict[str, Any]) -> Self:
        """Updates the current model object with the new fields"""
        for key, value in dict_values.items():
            setattr(self, key, value)
        return self

    def extract_db_fields(self) -> Dict[str, Any]:
        """
        Extacts all the db fields and excludes the related_names since those
        are simply relations.
        """
        related_names = self.meta.related_names
        return {k: v for k, v in self.__dict__.items() if k not in related_names}

    def __setattr__(self, key: Any, value: Any) -> Any:
        if key in self.fields:
            # Setting a relationship to a raw pk value should set a
            # fully-fledged relationship instance, with just the pk loaded.
            field = self.fields[key]

            if isinstance(field, saffier.ManyToManyField):
                value = getattr(self, settings.many_to_many_relation.format(key=key))
            else:
                value = self.fields[key].expand_relationship(value)
        super().__setattr__(key, value)

    def __get_instance_values(self, instance: Any) -> Set[Any]:
        return {
            v
            for k, v in instance.__dict__.items()
            if k in instance.fields.keys() and v is not None
        }

    def __eq__(self, other: Any) -> bool:
        if self.__class__ != other.__class__:
            return False
        original = self.__get_instance_values(instance=self)
        other_values = self.__get_instance_values(instance=other)
        if original != other_values:
            return False
        return True


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
    def build(cls, schema: Optional[str] = None) -> sqlalchemy.Table:
        """
        The inspect is done in an async manner and reflects the objects from the database.
        """
        metadata = cast("sqlalchemy.MetaData", cls.meta.registry._metadata)  # type: ignore
        metadata.schema = schema
        tablename: str = cast("str", cls.meta.tablename)
        return cls.reflect(tablename, metadata)

    @classmethod
    def reflect(cls, tablename: str, metadata: sqlalchemy.MetaData) -> sqlalchemy.Table:
        try:
            return sqlalchemy.Table(
                tablename, metadata, autoload_with=cls.meta.registry.sync_engine  # type: ignore
            )
        except Exception as e:
            raise ImproperlyConfigured(
                detail=f"Table with the name {tablename} does not exist."
            ) from e
