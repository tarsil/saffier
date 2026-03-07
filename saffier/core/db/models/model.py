import typing
from typing import Any, cast

import sqlalchemy
from sqlalchemy.engine.result import Row

import saffier
from saffier.conf import settings
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
        include: set[int] | set[str] | dict[int, typing.Any] | dict[str, typing.Any] | None = None,
        exclude: set[int] | set[str] | dict[int, typing.Any] | dict[str, typing.Any] | None = None,
        exclude_none: bool = False,
    ) -> dict[str, typing.Any]:
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

        db_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in self.fields and self.fields[key].has_column()
        }
        fields = {key: field.validator for key, field in self.fields.items() if key in db_kwargs}
        validator = Schema(fields=fields)
        db_kwargs = self._update_auto_now_fields(validator.check(db_kwargs), self.fields)

        if db_kwargs:
            pk_column = getattr(self.table.c, self.pkname)
            expression = self.table.update().values(**db_kwargs).where(pk_column == self.pk)
            await self.database.execute(expression)
        await self.signals.post_update.send(sender=self.__class__, instance=self)

        # Update the model instance.
        for key, value in kwargs.items():
            setattr(self, key, value)
        for key, value in db_kwargs.items():
            setattr(self, key, value)

        return self

    async def delete(self) -> int:
        """Delete operation from the database"""
        await self.signals.pre_delete.send(sender=self.__class__, instance=self)

        pk_column = getattr(self.table.c, self.pkname)
        count_expression = sqlalchemy.func.count().select().select_from(self.table)
        count_expression = count_expression.where(pk_column == self.pk)
        row_count = cast("int", await self.database.fetch_val(count_expression) or 0)

        expression = self.table.delete().where(pk_column == self.pk)
        await self.database.execute(expression)
        await self.signals.post_delete.send(
            sender=self.__class__, instance=self, row_count=row_count
        )
        return row_count

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
        autoincrement_value = await self.database.execute(expression)
        # sqlalchemy supports only one autoincrement column
        if autoincrement_value:
            column = self.table.autoincrement_column
            if column is not None and isinstance(autoincrement_value, Row):
                autoincrement_value = autoincrement_value._mapping[column.name]
            # can be explicit set, which causes an invalid value returned
            if column is not None and column.key not in kwargs:
                saffier_setattr(self, column.key, autoincrement_value)
        return self

    async def save(
        self,
        force_save: bool = False,
        values: typing.Any = None,
        **kwargs: typing.Any,
    ) -> type["Model"] | Any:
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
        is_create = getattr(self, "pk", None) is None or force_save

        fields = {
            key: field.validator for key, field in self.fields.items() if key in extracted_fields
        }
        if values:
            db_values = {
                key: value
                for key, value in values.items()
                if key in self.fields and self.fields[key].has_column()
            }
            if is_create:
                for key, field in self.fields.items():
                    if not field.has_column() or not field.validator.read_only:
                        continue
                    if key in extracted_fields:
                        expanded = field.expand_relationship(extracted_fields[key])
                        db_values[key] = field.validator.check(expanded)
                    elif field.validator.has_default():
                        db_values[key] = field.validator.get_default_value()
            kwargs = self._update_auto_now_fields(db_values, self.fields)
        else:
            validator = Schema(fields=fields)
            validated = validator.check(extracted_fields)
            if is_create:
                for key, field in self.fields.items():
                    if not field.has_column() or not field.validator.read_only:
                        continue
                    if key in extracted_fields:
                        expanded = field.expand_relationship(extracted_fields[key])
                        validated[key] = field.validator.check(expanded)
                    elif field.validator.has_default():
                        validated[key] = field.validator.get_default_value()
            kwargs = self._update_auto_now_fields(validated, self.fields)

        # Performs the update or the create based on a possible existing primary key
        if is_create:
            await self._save(**kwargs)
        else:
            await self.signals.pre_update.send(sender=self.__class__, instance=self, kwargs=kwargs)
            await self.update(**kwargs)
            await self.signals.post_update.send(sender=self.__class__, instance=self)

        # Refresh the results
        if any(
            field.server_default is not None
            for name, field in self.fields.items()
            if name not in extracted_fields
        ):
            await self.load()

        await self._persist_model_references()
        await self.signals.post_save.send(sender=self.__class__, instance=self)
        return self

    def __getattr__(self, name: str) -> Any:
        """
        Run an one off query to populate any foreign key making sure
        it runs only once per foreign key avoiding multiple database calls.
        """
        if name not in self.__dict__ and name in self.fields and name != self.pkname:
            field = self.fields[name]
            if getattr(field, "is_computed", False):
                return field.get_value(self, name)
            if field.is_virtual:
                if isinstance(field, saffier.ManyToManyField):
                    return getattr(self, settings.many_to_many_relation.format(key=name))
                if hasattr(field, "get_value"):
                    return field.get_value(self, name)
                raise AttributeError(name)
            run_sync(self.load())
            return self.__dict__[name]
        raise AttributeError(name)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self}>"

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.pkname}={self.pk})"


class StrictModel(Model):
    """
    Model variant that validates scalar field assignments and forbids ad-hoc public attributes.
    """

    class Meta:
        abstract = True
        registry = False

    def __setattr__(self, key: Any, value: Any) -> Any:
        if key in getattr(self, "fields", {}):
            field = self.fields[key]
            is_relationship = isinstance(
                field,
                (saffier.ForeignKey, saffier.OneToOneField, saffier.ManyToManyField),
            )
            if (
                not field.is_virtual
                and not is_relationship
                and not getattr(field, "is_computed", False)
            ):
                value = field.validator.check(value)
            return super().__setattr__(key, value)

        if key.startswith("_") or key in self.__dict__ or hasattr(type(self), key):
            return super().__setattr__(key, value)

        raise AttributeError(
            f"Unknown attribute '{key}' for strict model '{self.__class__.__name__}'."
        )


class ReflectModel(Model, SaffierBaseReflectModel):
    """
    Reflect on async engines is not yet supported, therefore, we need to make a sync_engine
    call.
    """
