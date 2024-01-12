import typing
from typing import Any, Type, Union

from saffier.core.db.models.base import SaffierBaseReflectModel
from saffier.core.db.models.mixins.generics import DeclarativeMixin
from saffier.core.db.models.row import ModelRow
from saffier.core.utils.schemas import Schema
from saffier.core.utils.sync import run_sync

saffier_setattr = object.__setattr__


class Model(ModelRow, DeclarativeMixin):
    """
    The models will always have an id attribute as primery key.
    The primary key can be whatever desired, from IntegerField, FloatField to UUIDField as long as the `id` field is explicitly declared or else it defaults to BigIntegerField.
    """

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

    def model_dump(
        self,
        include: Union[
            typing.Set[int],
            typing.Set[str],
            typing.Dict[int, typing.Any],
            typing.Dict[str, typing.Any],
            None,
        ] = None,
        exclude: Union[
            typing.Set[int],
            typing.Set[str],
            typing.Dict[int, typing.Any],
            typing.Dict[str, typing.Any],
            None,
        ] = None,
        exclude_none: bool = False,
    ) -> typing.Dict[str, typing.Any]:
        """
        Dumps the model in a dict format.
        """
        row_dict = {k: v for k, v in self.__dict__.items() if k in self.fields}

        if include is not None:
            row_dict = {k: v for k, v in row_dict.items() if k in include}
        if exclude is not None:
            row_dict = {k: v for k, v in row_dict.items() if k not in exclude}
        if exclude_none:
            row_dict = {k: v for k, v in row_dict.items() if v is not None}
        return row_dict

    async def update(self, **kwargs: typing.Any) -> typing.Any:
        """
        Update operation of the database fields.
        """
        await self.signals.pre_update.send(sender=self.__class__, instance=self)

        fields = {key: field.validator for key, field in self.fields.items() if key in kwargs}
        validator = Schema(fields=fields)
        kwargs = self._update_auto_now_fields(validator.check(kwargs), self.fields)
        pk_column = getattr(self.table.c, self.pkname)
        expression = self.table.update().values(**kwargs).where(pk_column == self.pk)
        await self.database.execute(expression)
        await self.signals.post_update.send(sender=self.__class__, instance=self)

        # Update the model instance.
        for key, value in kwargs.items():
            setattr(self, key, value)

        return self

    async def delete(self) -> None:
        """Delete operation from the database"""
        await self.signals.pre_delete.send(sender=self.__class__, instance=self)

        pk_column = getattr(self.table.c, self.pkname)
        expression = self.table.delete().where(pk_column == self.pk)

        await self.database.execute(expression)
        await self.signals.post_delete.send(sender=self.__class__, instance=self)

    async def load(self) -> None:
        # Build the select expression.
        pk_column = getattr(self.table.c, self.pkname)
        expression = self.table.select().where(pk_column == self.pk)

        # Perform the fetch.
        row = await self.database.fetch_one(expression)

        # Update the instance.
        for key, value in dict(row._mapping).items():
            setattr(self, key, value)

    async def _save(self, **kwargs: typing.Any) -> "Model":
        """
        Performs the save instruction.
        """
        expression = self.table.insert().values(**kwargs)
        awaitable = await self.database.execute(expression)
        if not awaitable:
            awaitable = kwargs.get(self.pkname)
        saffier_setattr(self, self.pkname, awaitable)
        return self

    async def _update(self, **kwargs: typing.Any) -> typing.Any:
        """
        Performs the save instruction.
        """
        pk_column = getattr(self.table.c, self.pkname)
        expression = self.table.update().values(**kwargs).where(pk_column == self.pk)
        awaitable = await self.database.execute(expression)
        return awaitable

    async def save(
        self: typing.Any,
        force_save: bool = False,
        values: typing.Any = None,
        **kwargs: typing.Any,
    ) -> Union[Type["Model"], Any]:
        """
        Performs a save of a given model instance.
        When creating a user it will make sure it can update existing or
        create a new one.
        """
        await self.signals.pre_save.send(sender=self.__class__, instance=self)

        extracted_fields = self.extract_db_fields()

        if getattr(self, "pk", None) is None and self.fields[self.pkname].autoincrement:
            extracted_fields.pop(self.pkname, None)

        self.update_from_dict(dict(extracted_fields.items()))

        fields = {
            key: field.validator for key, field in self.fields.items() if key in extracted_fields
        }
        if values:
            kwargs = self._update_auto_now_fields(values, self.fields)
        else:
            validator = Schema(fields=fields)
            kwargs = self._update_auto_now_fields(validator.check(extracted_fields), self.fields)

        # Performs the update or the create based on a possible existing primary key
        if getattr(self, "pk", None) is None or force_save:
            await self._save(**kwargs)
        else:
            await self.signals.pre_update.send(sender=self.__class__, instance=self, kwargs=kwargs)
            await self._update(**kwargs)
            await self.signals.post_update.send(sender=self.__class__, instance=self)

        # Refresh the results
        if any(
            field.server_default is not None
            for name, field in self.fields.items()
            if name not in extracted_fields
        ):
            await self.load()

        await self.signals.post_save.send(sender=self.__class__, instance=self)
        return self

    def __getattr__(self, name: str) -> Any:
        """
        Run an one off query to populate any foreign key making sure
        it runs only once per foreign key avoiding multiple database calls.
        """
        if name not in self.__dict__ and name in self.fields and name != self.pkname:
            run_sync(self.load())
            return self.__dict__[name]
        return super().__getattr__(name)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self}>"

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.pkname}={self.pk})"


class ReflectModel(Model, SaffierBaseReflectModel):
    """
    Reflect on async engines is not yet supported, therefore, we need to make a sync_engine
    call.
    """
