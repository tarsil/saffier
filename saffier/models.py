import typing
from dataclasses import field
from typing import Any

import sqlalchemy
import typesystem
from sqlalchemy.ext.asyncio import create_async_engine

from saffier.core.db import Database
from saffier.queryset import QuerySet
from saffier.types import DictAny
from saffier.utils import ModelUtil


class Registry:
    """
    Registers a database connection object
    """

    def __init__(self, database: Database) -> None:
        assert isinstance(
            database, Database
        ), "database must be an instance of saffier.core.db.Database"
        self.database = database
        self.models: DictAny = {}
        self._metadata = sqlalchemy.MetaData()

    @property
    def metadata(self):
        for model_class in self.models.values():
            model_class.build_table()
        return self._metadata

    def _get_database_url(self) -> str:
        url = self.database.url
        if not url.driver:
            if url.dialect == "postgressql":
                url = url.replace(driver="asyncpg")
            elif url.dialect == "mysql":
                url = url.replace(dricer="aiomysql")
            elif url.dialect == "sqlite":
                url = url.replace(driver="aiosqlite")
        return str(url)

    def _get_engine(self):
        url = self._get_database_url()
        engine = create_async_engine(url)
        return engine

    async def create_all(self):
        engine = self._get_engine()

        async with self.database:
            async with engine.begin() as connection:
                await connection.run_sync(self.metadata.create_all)

        await engine.dispose()

    async def drop_all(self):
        engine = self._get_engine()

        async with self.database:
            async with engine.begin() as conn:
                await conn.run_sync(self.metadata.drop_all)

        await engine.dispose()


class ModelMeta(type):
    """
    Metaclass for the Saffier models
    """

    def __new__(cls, name: str, bases: Any, attrs: Any):
        model_class = super().__new__(cls, name, bases, attrs)

        if "registry" in attrs:
            model_class.database = attrs["registry"].database
            attrs["registry"].models[name] = model_class

            if "tablename" not in attrs:
                tablename = f"{name.lower()}s"
                setattr(model_class, "tablename", tablename)

        for name, field in attrs.get("fields", {}).items():
            setattr(field, "registry", attrs.get("registry"))
            if field.primary_key:
                model_class.pkname = name

        return model_class

    @property
    def table(cls):
        if not hasattr(cls, "_table"):
            cls._table = cls.build_table()
        return cls._table

    @property
    def columns(cls) -> sqlalchemy.sql.ColumnCollection:
        return cls._table.columns


class AbstractModelMeta(metaclass=ModelMeta):
    ...


class Model(AbstractModelMeta, ModelUtil):
    query = QuerySet()

    def __init__(self, **kwargs: DictAny) -> None:
        if "pk" in kwargs:
            kwargs[self.pkname] = kwargs.pop("pk")
        for k, v in kwargs.items():
            if k not in self.fields:
                raise ValueError(f"Invalid keyword {k} for class {self.__class__.__name__}")
            setattr(self, k, v)

    @property
    def pk(self):
        return getattr(self, self.pkname)

    @pk.setter
    def pk(self, value):
        setattr(self, self.pkname, value)

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self}>"

    def __str__(self):
        return f"{self.__class__.__name__}({self.pkname}={self.pk})"

    @classmethod
    def build_table(cls):
        tablename = cls.tablename
        metadata = cls.registry._metadata
        columns = []
        for name, field in cls.fields.items():
            columns.append(field.get_column(name))
        return sqlalchemy.Table(tablename, metadata, *columns, extend_existing=True)

    @property
    def table(self) -> sqlalchemy.Table:
        return self.__class__.table

    async def update(self, **kwargs):
        fields = {key: field.validator for key, field in self.fields.items() if key in kwargs}
        validator = typesystem.Schema(fields=fields)
        kwargs = self._update_auto_now_fields(validator.validate(kwargs), self.fields)
        pk_column = getattr(self.table.c, self.pkname)
        expr = self.table.update().values(**kwargs).where(pk_column == self.pk)
        await self.database.execute(expr)

        # Update the model instance.
        for key, value in kwargs.items():
            setattr(self, key, value)

    async def delete(self) -> None:
        pk_column = getattr(self.table.c, self.pkname)
        expr = self.table.delete().where(pk_column == self.pk)

        await self.database.execute(expr)

    async def load(self):
        # Build the select expression.
        pk_column = getattr(self.table.c, self.pkname)
        expr = self.table.select().where(pk_column == self.pk)

        # Perform the fetch.
        row = await self.database.fetch_one(expr)

        # Update the instance.
        for key, value in dict(row._mapping).items():
            setattr(self, key, value)

    @classmethod
    def _from_row(cls, row, select_related=[]):
        """
        Instantiate a model instance, given a database row.
        """
        item = {}

        # Instantiate any child instances first.
        for related in select_related:
            if "__" in related:
                first_part, remainder = related.split("__", 1)
                model_cls = cls.fields[first_part].target
                item[first_part] = model_cls._from_row(row, select_related=[remainder])
            else:
                model_cls = cls.fields[related].target
                item[related] = model_cls._from_row(row)

        # Pull out the regular column values.
        for column in cls.table.columns:
            if column.name not in item:
                item[column.name] = row[column]

        return cls(**item)

    def __setattr__(self, key, value):
        if key in self.fields:
            # Setting a relationship to a raw pk value should set a
            # fully-fledged relationship instance, with just the pk loaded.
            value = self.fields[key].expand_relationship(value)
        super().__setattr__(key, value)

    def __eq__(self, other):
        if self.__class__ != other.__class__:
            return False
        for key in self.fields.keys():
            if getattr(self, key, None) != getattr(other, key, None):
                return False
        return True
