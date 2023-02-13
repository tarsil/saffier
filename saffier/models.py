import sqlalchemy

from saffier.core.metaclass import MetaInfo, ModelMeta
from saffier.core.schemas import Schema
from saffier.core.utils import ModelUtil
from saffier.managers import ModelManager
from saffier.types import DictAny


class Model(ModelMeta, ModelUtil):
    """
    The models will always have an id attribute as primery key.
    The primary key can be whatever desired, from IntegerField, FloatField to UUIDField as long as the `id` field is explicitly declared or else it defaults to BigIntegerField.
    """

    query = ModelManager()
    _meta = MetaInfo(None)

    def __init__(self, **kwargs: DictAny) -> None:
        if "pk" in kwargs:
            kwargs[self.pkname] = kwargs.pop("pk")
        for k, v in kwargs.items():
            if k not in self.fields:
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
                    unique_together = (("field_a", "field_b"))

        """

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
        tablename = cls._meta.tablename
        metadata = cls._meta.registry._metadata
        columns = []
        for name, field in cls.fields.items():
            columns.append(field.get_column(name))
        return sqlalchemy.Table(tablename, metadata, *columns, extend_existing=True)

    @property
    def table(self) -> sqlalchemy.Table:
        return self.__class__.table

    async def update(self, **kwargs):
        fields = {key: field.validator for key, field in self.fields.items() if key in kwargs}
        validator = Schema(fields=fields)
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
