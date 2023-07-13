import functools
import typing

import sqlalchemy
from sqlalchemy.engine import Engine

from saffier.core.schemas import Schema
from saffier.db.models.manager import Manager
from saffier.db.models.metaclass import MetaInfo, ModelMeta, ReflectMeta
from saffier.exceptions import ImproperlyConfigured
from saffier.mixins.models import DeclarativeMixin, ModelBuilder

M = typing.TypeVar("M", bound="Model")


class Model(ModelMeta, ModelBuilder, DeclarativeMixin):
    """
    The models will always have an id attribute as primery key.
    The primary key can be whatever desired, from IntegerField, FloatField to UUIDField as long as the `id` field is explicitly declared or else it defaults to BigIntegerField.
    """

    query = Manager()
    _meta = MetaInfo(None)
    _db_model: bool = False
    _raw_query: typing.Optional[str] = None

    def __init__(self, **kwargs: typing.Any) -> None:
        if "pk" in kwargs:
            kwargs[self.pkname] = kwargs.pop("pk")

        for k, v in kwargs.items():
            if k not in self.fields:
                if not hasattr(self, k):
                    raise ValueError(f"Invalid keyword {k} for class {self.__class__.__name__}")
            setattr(self, k, v)

    class Meta:
        """
        The `Meta` class used to configure each metadata of the model.
        Abstract classes are not generated in the database, instead, they are simply used as
        a reference for field generation.

        Usage:

        .. code-block:: python3

            class User(Model):
                ...

                class Meta:
                    registry = models
                    tablename = "users"

        """

    async def update(self, **kwargs: typing.Any) -> typing.Any:
        """
        Update operation of the database fields.
        """
        fields = {key: field.validator for key, field in self.fields.items() if key in kwargs}
        validator = Schema(fields=fields)
        kwargs = self._update_auto_now_fields(validator.check(kwargs), self.fields)
        pk_column = getattr(self.table.c, self.pkname)
        expression = self.table.update().values(**kwargs).where(pk_column == self.pk)
        await self.database.execute(expression)

        # Update the model instance.
        for key, value in kwargs.items():
            setattr(self, key, value)

    async def delete(self) -> None:
        """Delete operation from the database"""
        pk_column = getattr(self.table.c, self.pkname)
        expression = self.table.delete().where(pk_column == self.pk)

        await self.database.execute(expression)

    async def load(self) -> None:
        # Build the select expression.
        pk_column = getattr(self.table.c, self.pkname)
        expression = self.table.select().where(pk_column == self.pk)

        # Perform the fetch.
        row = await self.database.fetch_one(expression)

        # Update the instance.
        for key, value in dict(row._mapping).items():
            setattr(self, key, value)

    async def save(self: M) -> M:
        """
        Performs a save of a given model instance.
        When creating a user it will make sure it can update existing or
        create a new one.
        """
        extracted_fields = self.extract_db_fields()

        if getattr(self, "pk", None) is None and self.fields[self.pkname].autoincrement:
            extracted_fields.pop(self.pkname, None)

        self.update_from_dict(dict(extracted_fields.items()))

        fields = {
            key: field.validator for key, field in self.fields.items() if key in extracted_fields
        }
        validator = Schema(fields=fields)
        kwargs = self._update_auto_now_fields(validator.check(extracted_fields), self.fields)

        # Performs the update or the create based on a possible existing primary key
        if getattr(self, "pk", None) is None:
            expression = self.table.insert().values(**kwargs)
            pk_column = await self.database.execute(expression)
            setattr(self, self.pkname, pk_column)
        else:
            pk_column = getattr(self.table.c, self.pkname)
            expression = self.table.update().values(**kwargs).where(pk_column == self.pk)
            await self.database.execute(expression)

        # Refresh the results
        if any(
            field.server_default is not None
            for name, field in self.fields.items()
            if name not in extracted_fields
        ):
            await self.load()
        return self

    @classmethod
    def from_query_result(cls, row: typing.Any, select_related: typing.Any = None) -> "Model":
        """
        Instantiate a model instance, given a database row.
        """
        item = {}

        if not select_related:
            select_related = []

        # Instantiate any child instances first.
        for related in select_related:
            if "__" in related:
                first_part, remainder = related.split("__", 1)
                try:
                    model_cls = cls.fields[first_part].target
                except KeyError:
                    model_cls = getattr(cls, first_part).related_from

                item[first_part] = model_cls.from_query_result(row, select_related=[remainder])
            else:
                try:
                    model_cls = cls.fields[related].target
                except KeyError:
                    model_cls = getattr(cls, related).related_from
                item[related] = model_cls.from_query_result(row)

        # Pull out the regular column values.
        for column in cls.table.columns:
            # Making sure when a table is reflected, maps the right fields of the ReflectModel
            if column.name not in cls.fields.keys():
                continue

            elif column.name not in item:
                item[column.name] = row[column]

        return cls(**item)


class ReflectModel(ReflectMeta, Model):
    """
    Reflect on async engines is not yet supported, therefore, we need to make a sync_engine
    call.
    """

    @classmethod
    @functools.lru_cache
    def get_engine(cls, url: str) -> Engine:
        return sqlalchemy.create_engine(url)

    @property
    def pk(self) -> typing.Any:
        return getattr(self, self.pkname, None)

    @pk.setter
    def pk(self, value: typing.Any) -> typing.Any:
        setattr(self, self.pkname, value)

    @classmethod
    def build_table(cls) -> typing.Any:
        """
        The inspect is done in an async manner and reflects the objects from the database.
        """
        metadata = cls._meta.registry._metadata  # type: ignore
        tablename = cls._meta.tablename
        return cls.reflect(tablename, metadata)

    @classmethod
    def reflect(cls, tablename, metadata):
        try:
            return sqlalchemy.Table(
                tablename, metadata, autoload_with=cls._meta.registry.sync_engine
            )
        except Exception as e:
            raise ImproperlyConfigured(
                detail=f"Table with the name {tablename} does not exist."
            ) from e
