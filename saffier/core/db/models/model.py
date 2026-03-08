import copy
import typing
from collections.abc import Sequence
from typing import Any, cast

import orjson
import sqlalchemy
from sqlalchemy.engine.result import Row
from sqlalchemy.sql.elements import ColumnElement

import saffier
from saffier.conf import settings
from saffier.core.db.context_vars import CURRENT_INSTANCE, EXPLICIT_SPECIFIED_VALUES
from saffier.core.db.models.base import SaffierBaseReflectModel
from saffier.core.db.models.mixins.admin import AdminMixin
from saffier.core.db.models.mixins.generics import DeclarativeMixin
from saffier.core.db.models.row import ModelRow
from saffier.core.utils.db import check_db_connection
from saffier.core.utils.schemas import Schema
from saffier.core.utils.sync import run_sync

saffier_setattr = object.__setattr__


class Model(ModelRow, DeclarativeMixin, AdminMixin):
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

    @classmethod
    def model_json_schema(
        cls,
        *,
        schema_generator: Any | None = None,
        mode: str | None = None,
        phase: str | None = None,
        include_callable_defaults: bool | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del kwargs
        if phase is None:
            phase = "create" if mode == "validation" else "view"
        if include_callable_defaults is None:
            marker = getattr(schema_generator, "include_callable_defaults", None)
            if marker is None:
                schema_name = getattr(schema_generator, "__name__", "")
                include_callable_defaults = schema_name != "NoCallableDefaultJsonSchema"
            else:
                include_callable_defaults = bool(marker)
        marshall_class = cls.get_admin_marshall_class(phase=phase, for_schema=True)
        return marshall_class.model_json_schema(
            include_callable_defaults=bool(include_callable_defaults)
        )

    def __getattribute__(self, name: str) -> Any:
        value = super().__getattribute__(name)
        if value is not None or name.startswith("_"):
            return value

        try:
            fields = object.__getattribute__(self, "fields")
        except AttributeError:
            return value

        field = fields.get(name) if isinstance(fields, dict) else None
        if (
            field is not None
            and getattr(field, "null", False)
            and isinstance(field, (saffier.ForeignKey, saffier.OneToOneField))
        ):
            return None
        return value

    def model_dump(
        self,
        include: set[int] | set[str] | dict[int, typing.Any] | dict[str, typing.Any] | None = None,
        exclude: set[int] | set[str] | dict[int, typing.Any] | dict[str, typing.Any] | None = None,
        exclude_none: bool = False,
        _seen: set[int] | None = None,
    ) -> dict[str, typing.Any]:
        """
        Dumps the model in a dict format.
        """
        seen = set() if _seen is None else _seen
        seen.add(id(self))

        def is_included(
            field_name: str,
            include_rule: set[int]
            | set[str]
            | dict[int, typing.Any]
            | dict[str, typing.Any]
            | None,
        ) -> bool:
            if include_rule is None:
                return True
            if isinstance(include_rule, dict):
                return field_name in include_rule and include_rule[field_name] is not False
            return field_name in include_rule

        def is_excluded(
            field_name: str,
            exclude_rule: set[int]
            | set[str]
            | dict[int, typing.Any]
            | dict[str, typing.Any]
            | None,
        ) -> bool:
            if exclude_rule is None:
                return False
            if isinstance(exclude_rule, dict):
                return exclude_rule.get(field_name) is True
            return field_name in exclude_rule

        def nested_rule(
            rule: set[int] | set[str] | dict[int, typing.Any] | dict[str, typing.Any] | None,
            field_name: str,
        ) -> typing.Any:
            if not isinstance(rule, dict):
                return None
            value = rule.get(field_name)
            if value in (None, True, False):
                return None
            return value

        def serialize(
            value: typing.Any,
            *,
            sub_include: typing.Any = None,
            sub_exclude: typing.Any = None,
        ) -> typing.Any:
            if hasattr(value, "model_dump") and callable(value.model_dump):
                if id(value) in seen:
                    return getattr(value, "pk", None)
                try:
                    return value.model_dump(
                        include=sub_include,
                        exclude=sub_exclude,
                        exclude_none=exclude_none,
                        _seen=seen,
                    )
                except TypeError:
                    kwargs: dict[str, typing.Any] = {"exclude_none": exclude_none}
                    if sub_include is not None:
                        kwargs["include"] = sub_include
                    if sub_exclude is not None:
                        kwargs["exclude"] = sub_exclude
                    return value.model_dump(**kwargs)

            if isinstance(value, dict):
                return {key: serialize(inner_value) for key, inner_value in value.items()}

            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                return [serialize(item) for item in value]

            return value

        row_dict: dict[str, typing.Any] = {}

        for field_name, field in self.fields.items():
            if isinstance(field, saffier.ManyToManyField):
                continue
            if getattr(field, "exclude", False):
                continue
            if not is_included(field_name, include) or is_excluded(field_name, exclude):
                continue

            if field_name in self.__dict__:
                value = self.__dict__[field_name]
            elif getattr(field, "is_computed", False):
                try:
                    value = getattr(self, field_name)
                except AttributeError:
                    continue
            else:
                continue

            value = serialize(
                value,
                sub_include=nested_rule(include, field_name),
                sub_exclude=nested_rule(exclude, field_name),
            )
            if exclude_none and value is None:
                continue
            row_dict[field_name] = value

        return row_dict

    def model_dump_json(
        self,
        include: set[int] | set[str] | dict[int, typing.Any] | dict[str, typing.Any] | None = None,
        exclude: set[int] | set[str] | dict[int, typing.Any] | dict[str, typing.Any] | None = None,
        exclude_none: bool = False,
    ) -> str:
        """
        Dumps the model into a JSON string.
        """
        return orjson.dumps(
            self.model_dump(include=include, exclude=exclude, exclude_none=exclude_none),
            option=orjson.OPT_NON_STR_KEYS,
        ).decode("utf-8")

    async def execute_pre_save_hooks(
        self,
        field_values: dict[str, typing.Any],
        original_values: dict[str, typing.Any] | None = None,
        *,
        is_update: bool,
    ) -> dict[str, typing.Any]:
        hook_values: dict[str, typing.Any] = {}
        token = CURRENT_INSTANCE.set(self)
        try:
            all_field_names = {*field_values.keys(), *((original_values or {}).keys())}
            for field_name in all_field_names:
                field = self.fields.get(field_name)
                if field is None:
                    continue
                pre_save_callback = getattr(field, "pre_save_callback", None)
                if not callable(pre_save_callback):
                    continue
                hook_values.update(
                    await pre_save_callback(
                        field_values.get(field_name),
                        (original_values or {}).get(field_name),
                        is_update=is_update,
                    )
                )
            return hook_values
        finally:
            CURRENT_INSTANCE.reset(token)

    def _should_force_insert(self) -> bool:
        for field_name in type(self).pknames:
            field = self.fields.get(field_name)
            if field is None:
                continue
            value = getattr(self, field_name, None)
            column = getattr(self.table.c, field_name, None)
            if value is None and column is not None and getattr(column, "autoincrement", False):
                return True
            if getattr(field, "increment_on_save", 0) != 0 or getattr(field, "auto_now", False):
                return True
            if getattr(field, "auto_now_add", False) and value is None:
                return True
        return False

    def _apply_persisted_db_values(self, db_kwargs: dict[str, typing.Any]) -> None:
        grouped_values: dict[str, dict[str, typing.Any]] = {}

        for key, value in db_kwargs.items():
            field_name = self.meta.columns_to_field.get(key)
            if field_name is None:
                field_name = key if key in self.fields else None
            if field_name is None or field_name not in self.fields:
                continue
            grouped_values.setdefault(field_name, {})[key] = value

        for field_name, field_values in grouped_values.items():
            field = self.fields[field_name]
            if getattr(field, "increment_on_save", 0) != 0 and any(
                isinstance(value, ColumnElement) for value in field_values.values()
            ):
                self.__dict__.pop(field_name, None)
                continue

            payload = dict(field_values)
            field.modify_input(field_name, payload)

            resolved_value = payload.get(field_name)
            if resolved_value is None and len(field_values) == 1:
                resolved_value = next(iter(field_values.values()))

            if isinstance(field, (saffier.ForeignKey, saffier.OneToOneField)):
                current_value = self.__dict__.get(field_name)
                if current_value is not None and hasattr(current_value, "pk"):
                    if resolved_value is None:
                        self.__dict__[field_name] = None
                        continue
                    try:
                        current_value.pk = (
                            getattr(resolved_value, "pk", resolved_value)
                            if not isinstance(resolved_value, dict)
                            else resolved_value
                        )
                        continue
                    except Exception:
                        pass

            if field_name in payload:
                setattr(self, field_name, payload[field_name])
                continue

            if len(field_values) == 1:
                setattr(self, field_name, next(iter(field_values.values())))

    async def update(self, **kwargs: typing.Any) -> typing.Any:
        """
        Update operation of the database fields.
        """
        await self.signals.pre_update.send(sender=self.__class__, instance=self)

        normalized_kwargs = self.__class__.normalize_field_kwargs(kwargs)
        original_field_values = {
            key: getattr(self, key, None) for key in normalized_kwargs if key in self.fields
        }
        self.update_from_dict(normalized_kwargs)
        field_values = {key: getattr(self, key) for key in normalized_kwargs if key in self.fields}
        db_kwargs = {
            key: value for key, value in field_values.items() if self.fields[key].has_column()
        }
        fields = {}
        for key, field in self.fields.items():
            if key not in db_kwargs:
                continue
            field_validator = field.validator
            if field_validator.read_only:
                field_validator = copy.copy(field_validator)
                field_validator.read_only = False
            fields[key] = field_validator
        validator = Schema(fields=fields)
        token = EXPLICIT_SPECIFIED_VALUES.set(set(normalized_kwargs.keys()))
        try:
            hook_values = await self.execute_pre_save_hooks(
                field_values,
                original_field_values,
                is_update=True,
            )
        finally:
            EXPLICIT_SPECIFIED_VALUES.reset(token)
        validated_kwargs = validator.check(db_kwargs)
        db_kwargs = self.__class__.extract_column_values(
            validated_kwargs,
            is_update=True,
            is_partial=True,
            phase="prepare_update",
            instance=self,
            model_instance=self,
        )
        db_kwargs.update(hook_values)
        db_kwargs = self._update_auto_now_fields(db_kwargs, self.fields)

        if db_kwargs:
            expression = self.table.update().values(**db_kwargs).where(*self.identifying_clauses())
            check_db_connection(self.database)
            async with self.database as database:
                await database.execute(expression)
        await self.signals.post_update.send(sender=self.__class__, instance=self)
        self._apply_persisted_db_values(db_kwargs)

        return self

    async def _delete_forward_references(self, ignore_fields: set[str]) -> None:
        has_forward_reference_cleanup = any(
            getattr(field, "remove_referenced", False)
            for field in self.meta.foreign_key_fields.values()
        )
        if has_forward_reference_cleanup and self.can_load and not self._has_loaded_db_fields():
            await self.load(only_needed=True)

        for field_name, field in self.meta.foreign_key_fields.items():
            related_name = getattr(field, "related_name", None)
            if (
                field_name in ignore_fields
                or related_name in ignore_fields
                or not getattr(field, "remove_referenced", False)
            ):
                continue

            value = self.__dict__.get(field_name)
            if value is None:
                continue

            related = field.expand_relationship(value)
            if related is None:
                continue
            if hasattr(related, "can_load") and not related.can_load:
                continue

            remove_call: str | bool = related_name or True
            raw_delete = getattr(related, "raw_delete", None)
            if callable(raw_delete):
                await raw_delete(
                    skip_post_delete_hooks=False,
                    remove_referenced_call=remove_call,
                )
            else:
                await related.delete()

    async def _delete_reverse_relations(self, ignore_fields: set[str]) -> None:
        for related_name, related_field in self.meta.related_fields.items():
            if related_name in ignore_fields:
                continue
            if getattr(self.__class__, related_name, None) is None:
                continue

            foreign_key_name = related_field.get_foreign_key_field_name()
            foreign_key = related_field.related_from.fields.get(foreign_key_name)
            if foreign_key is None:
                continue

            should_cascade = getattr(foreign_key, "force_cascade_deletion_relation", False) or (
                getattr(foreign_key, "no_constraint", False)
                and getattr(foreign_key, "on_delete", None) == saffier.CASCADE
            )
            if not should_cascade:
                continue

            queryset = getattr(self, related_name)
            schema_name = getattr(self, "schema_name", None)
            if schema_name is not None and hasattr(queryset, "using"):
                queryset = queryset.using(schema=schema_name)
            await queryset.raw_delete(
                use_models=getattr(foreign_key, "use_model_based_deletion", False),
                remove_referenced_call=related_name,
            )

    async def raw_delete(
        self,
        *,
        skip_post_delete_hooks: bool = False,
        remove_referenced_call: bool | str = False,
    ) -> int:
        del skip_post_delete_hooks
        if getattr(self, "_db_deleted", False):
            return 0

        if self.__deletion_with_signals__ and remove_referenced_call:
            await self.signals.pre_delete.send(
                sender=self.__class__,
                instance=self,
                model_instance=self,
            )

        count_expression = sqlalchemy.func.count().select().select_from(self.table)
        count_expression = count_expression.where(*self.identifying_clauses())
        check_db_connection(self.database)
        async with self.database as database:
            row_count = cast("int", await database.fetch_val(count_expression) or 0)

        if row_count:
            expression = self.table.delete().where(*self.identifying_clauses())
            async with self.database as database:
                await database.execute(expression)

        self.__dict__["_db_deleted"] = bool(row_count)

        ignore_fields: set[str] = set()
        if isinstance(remove_referenced_call, str):
            ignore_fields.add(remove_referenced_call)

        if row_count:
            await self._delete_forward_references(ignore_fields)
            if not getattr(self, "__skip_generic_reverse_delete__", False):
                await self._delete_reverse_relations(ignore_fields)

        if self.__deletion_with_signals__ and remove_referenced_call:
            await self.signals.post_delete.send(
                sender=self.__class__,
                instance=self,
                model_instance=self,
                row_count=row_count,
            )
        return row_count

    async def delete(self, skip_post_delete_hooks: bool = False) -> int:
        """Delete operation from the database"""
        await self.signals.pre_delete.send(
            sender=self.__class__,
            instance=self,
            model_instance=self,
        )

        row_count = await self.raw_delete(
            skip_post_delete_hooks=skip_post_delete_hooks,
            remove_referenced_call=False,
        )

        await self.signals.post_delete.send(
            sender=self.__class__,
            instance=self,
            model_instance=self,
            row_count=row_count,
        )
        return row_count

    async def load(self, only_needed: bool = False) -> None:
        if only_needed and self._has_loaded_db_fields():
            return

        # Build the select expression.
        expression = self.table.select().where(*self.identifying_clauses())

        # Perform the fetch.
        check_db_connection(self.database)
        async with self.database as database:
            row = await database.fetch_one(expression)

        if row is None:
            return

        loaded = self.__class__.from_query_result(
            row,
            using_schema=self.get_active_instance_schema(),
        )
        for key, value in loaded.__dict__.items():
            if key.startswith("_"):
                self.__dict__[key] = value
                continue
            setattr(self, key, value)

    async def _save(self, **kwargs: typing.Any) -> "Model":
        """
        Performs the save instruction.
        """
        expression = self.table.insert().values(**kwargs)
        check_db_connection(self.database)
        async with self.database as database:
            autoincrement_value = await database.execute(expression)
        persisted_values = dict(kwargs)
        # sqlalchemy supports only one autoincrement column
        if autoincrement_value:
            column = self.table.autoincrement_column
            if column is not None and isinstance(autoincrement_value, Row):
                mapping = autoincrement_value._mapping
                autoincrement_value = mapping.get(column.key, mapping.get(column.name))
            # can be explicit set, which causes an invalid value returned
            if column is not None and column.key not in kwargs:
                persisted_values[column.key] = autoincrement_value
        self._apply_persisted_db_values(persisted_values)
        for field_name, field in self.fields.items():
            if field_name in self.__dict__:
                continue
            if not getattr(field, "null", False):
                continue
            if isinstance(field, (saffier.ForeignKey, saffier.OneToOneField)):
                self.__dict__[field_name] = None
        return self

    async def save(
        self,
        force_save: bool | None = None,
        values: typing.Any = None,
        force_insert: bool | None = None,
        **kwargs: typing.Any,
    ) -> type["Model"] | Any:
        """
        Performs a save of a given model instance.
        When creating a user it will make sure it can update existing or
        create a new one.
        """
        if force_insert is None:
            force_insert = bool(force_save)
        self.__dict__["_saffier_save_in_progress"] = True
        try:
            await self.signals.pre_save.send(sender=self.__class__, instance=self)

            extracted_fields = self.extract_db_fields()
            original_extracted_fields = dict(extracted_fields)
            explicit_field_values: dict[str, typing.Any] | None = None
            explicit_field_names: set[str] = set()

            if getattr(self, "pk", None) is None and self.fields[self.pkname].autoincrement:
                extracted_fields.pop(self.pkname, None)
            else:
                for field_name in type(self).pknames:
                    field = self.fields[field_name]
                    if field.autoincrement and getattr(self, field_name, None) is None:
                        extracted_fields.pop(field_name, None)

            if isinstance(values, (set, list, tuple)):
                explicit_field_names = set(values)
                values = None

            if values:
                normalized_values = self.__class__.normalize_field_kwargs(values)
                self.update_from_dict(normalized_values)
                explicit_field_values = {
                    key: getattr(self, key) for key in normalized_values if key in self.fields
                }
                explicit_field_names = set(explicit_field_values)
                extracted_fields.update(explicit_field_values)

            self.update_from_dict(dict(extracted_fields.items()))
            is_create = bool(force_insert) or not self.can_load or self._should_force_insert()
            token = EXPLICIT_SPECIFIED_VALUES.set(explicit_field_names)
            try:
                hook_values = await self.execute_pre_save_hooks(
                    extracted_fields,
                    original_extracted_fields,
                    is_update=not is_create,
                )
            finally:
                EXPLICIT_SPECIFIED_VALUES.reset(token)

            input_values = (
                extracted_fields
                if is_create or explicit_field_values is None
                else explicit_field_values
            )
            fields = {}
            for key, field in self.fields.items():
                if key not in input_values:
                    continue
                field_validator = field.validator
                if field_validator.read_only:
                    field_validator = copy.copy(field_validator)
                    field_validator.read_only = False
                fields[key] = field_validator
            validator = Schema(fields=fields)
            validated = validator.check(input_values)
            kwargs = self.__class__.extract_column_values(
                validated,
                is_update=not is_create,
                is_partial=not is_create and explicit_field_values is not None,
                phase="prepare_insert" if is_create else "prepare_update",
                instance=self,
                model_instance=self,
            )
            kwargs.update(hook_values)
            kwargs = self._update_auto_now_fields(kwargs, self.fields)

            # Performs the update or the create based on a possible existing primary key
            if is_create:
                await self._save(**kwargs)
            else:
                await self.signals.pre_update.send(
                    sender=self.__class__, instance=self, kwargs=kwargs
                )
                if kwargs:
                    expression = (
                        self.table.update().values(**kwargs).where(*self.identifying_clauses())
                    )
                    check_db_connection(self.database)
                    async with self.database as database:
                        await database.execute(expression)
                await self.signals.post_update.send(sender=self.__class__, instance=self)
                self._apply_persisted_db_values(kwargs)

            # Refresh the results
            if any(
                field.server_default is not None
                for name, field in self.fields.items()
                if name not in extracted_fields
            ):
                await self.load()

            await self._persist_model_references()
            await self._persist_related_fields()
            await self.signals.post_save.send(sender=self.__class__, instance=self)
            return self
        finally:
            self.__dict__.pop("_saffier_save_in_progress", None)

    async def real_save(
        self,
        force_insert: bool = False,
        values: typing.Any = None,
        force_save: bool | None = None,
        **kwargs: typing.Any,
    ) -> type["Model"] | Any:
        if force_save is not None:
            force_insert = force_save
        return await self.save(force_insert=force_insert, values=values, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """
        Run an one off query to populate any foreign key making sure
        it runs only once per foreign key avoiding multiple database calls.
        """
        if name not in self.__dict__ and name in self.fields and name not in type(self).pknames:
            field = self.fields[name]
            if getattr(field, "is_computed", False):
                return field.get_value(self, name)
            if field.is_virtual:
                if isinstance(field, saffier.ManyToManyField):
                    return getattr(self, settings.many_to_many_relation.format(key=name))
                if hasattr(field, "get_value"):
                    return field.get_value(self, name)
                raise AttributeError(name)
            if name in getattr(self, "__no_load_trigger_attrs__", set()):
                raise AttributeError(name)
            run_sync(self.load())
            return self.__dict__[name]
        raise AttributeError(name)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self}>"

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.join_identifiers_to_string()})"


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

        plain_fields = getattr(type(self), "__plain_model_fields__", {})
        if key in plain_fields:
            value = type(self).validate_plain_field_value(key, value)
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
