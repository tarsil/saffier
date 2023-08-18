import functools
from typing import Any, ClassVar, Dict, Optional, Sequence, cast

import sqlalchemy
from sqlalchemy.engine import Engine
from typing_extensions import Self

import saffier
from saffier.conf import settings
from saffier.core.db.datastructures import Index, UniqueConstraint
from saffier.core.db.models.managers import Manager
from saffier.core.db.models.metaclasses import BaseModelMeta, BaseModelReflectMeta, MetaInfo
from saffier.core.utils.model import DateParser
from saffier.exceptions import ImproperlyConfigured


class SaffierBaseModel(DateParser, metaclass=BaseModelMeta):
    """
    All the operations performed by the model added to
    a common mixin.
    """

    query: ClassVar[Manager] = Manager()
    meta: ClassVar[MetaInfo] = MetaInfo(None)
    __db_model__: ClassVar[bool] = False
    __raw_query__: ClassVar[Optional[str]] = None

    @property
    def pk(self) -> Any:
        return getattr(self, self.pkname)

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

    def __eq__(self, other: Any) -> bool:
        if self.__class__ != other.__class__:
            return False
        for key in self.fields.keys():
            if getattr(self, key, None) != getattr(other, key, None):
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
