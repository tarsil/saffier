from collections.abc import Mapping
from functools import cached_property
from typing import Any, cast

import sqlalchemy
from sqlalchemy import Engine
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from sqlalchemy.orm import declarative_base as sa_declarative_base

from saffier.core.connection.database import Database
from saffier.core.connection.schemas import Schema
from saffier.core.db.constants import CASCADE


class Registry:
    """
    The command center for the models being generated
    for Saffier.
    """

    def __init__(
        self,
        database: Database,
        *,
        with_content_type: bool | type[Any] = False,
        **kwargs: Any,
    ) -> None:
        self.database: Database = database
        self.models: dict[str, Any] = {}
        self.reflected: dict[str, Any] = {}
        self.pattern_models: dict[str, Any] = {}
        self.content_type: Any | None = None
        self.db_schema = kwargs.get("schema")
        self.extra: Mapping[str, Database] = kwargs.pop("extra", {})
        self._pattern_reflected_dbs: set[str | None] = set()
        self._content_type_models_bound: set[str] = set()

        self.schema = Schema(registry=self)

        self._metadata = (
            sqlalchemy.MetaData(schema=self.db_schema)
            if self.db_schema is not None
            else sqlalchemy.MetaData()
        )

        if with_content_type is not False:
            self._set_content_type(with_content_type)

    def _set_content_type(self, with_content_type: bool | type[Any]) -> None:
        from saffier.contrib.contenttypes.models import ContentType

        content_type_model = ContentType if with_content_type is True else with_content_type
        if not isinstance(content_type_model, type):
            raise TypeError("with_content_type must be True/False or a model type.")

        if getattr(content_type_model.meta, "abstract", False):
            meta = type(
                "Meta",
                (),
                {
                    "registry": self,
                    "tablename": "contenttypes",
                },
            )
            content_type_model = type("ContentType", (content_type_model,), {"Meta": meta})
        elif getattr(content_type_model.meta, "registry", None) is not self:
            meta = type(
                "Meta",
                (),
                {
                    "registry": self,
                    "tablename": getattr(content_type_model.meta, "tablename", "contenttypes"),
                },
            )
            content_type_model = type("ContentType", (content_type_model,), {"Meta": meta})

        self.content_type = content_type_model
        self._attach_content_type_to_registered_models()

    def _attach_content_type_to_registered_models(self) -> None:
        if self.content_type is None:
            return
        for model in self.models.values():
            self._attach_content_type_to_model(model)

    def _handle_model_registration(self, model_class: type[Any]) -> None:
        if self.content_type is None:
            return
        self._attach_content_type_to_model(model_class)

    def _attach_content_type_to_model(self, model_class: type[Any]) -> None:
        if self.content_type is None:
            return
        if model_class in (self.content_type, getattr(self.content_type, "proxy_model", None)):
            return
        if getattr(model_class.meta, "abstract", False):
            return
        if getattr(model_class, "is_proxy_model", False):
            return
        if model_class.__name__ in self.reflected:
            return

        from saffier.contrib.contenttypes.fields import ContentTypeField
        from saffier.core.db.models.metaclasses import _set_related_name_for_foreign_keys

        if "content_type" in model_class.fields:
            if isinstance(model_class.fields["content_type"], ContentTypeField):
                self._bind_content_type_pre_save(model_class)
            return

        has_content_type_field = any(
            isinstance(field, ContentTypeField) for field in model_class.fields.values()
        )
        if has_content_type_field:
            self._bind_content_type_pre_save(model_class)
            return

        related_name = f"reverse_{model_class.__name__.lower()}"
        if hasattr(self.content_type, related_name):
            raise RuntimeError(
                f"Duplicate related content type name generated: {related_name!r} for {model_class!r}"
            )

        field = ContentTypeField(
            to=self.content_type,
            related_name=related_name,
            on_delete=CASCADE,
        )
        field.owner = model_class
        field.registry = self
        model_class.fields["content_type"] = field
        model_class.meta.fields["content_type"] = field
        model_class.meta.fields_mapping["content_type"] = field
        model_class.meta.foreign_key_fields["content_type"] = field

        model_related_names = _set_related_name_for_foreign_keys(
            {"content_type": field},
            cast(Any, model_class),
        )
        model_class.meta.related_names.update(model_related_names)

        self._bind_content_type_pre_save(model_class)

        model_class._table = None
        model_class.__proxy_model__ = None
        proxy_model = model_class.generate_proxy_model()
        model_class.__proxy_model__ = proxy_model
        model_class.__proxy_model__.parent = model_class

    def _bind_content_type_pre_save(self, model_class: type[Any]) -> None:
        if model_class.__name__ in self._content_type_models_bound:
            return
        if self.content_type is None:
            return
        from saffier.contrib.contenttypes.fields import ContentTypeField

        async def ensure_content_type(
            sender: type[Any],
            instance: Any,
            **kwargs: Any,
        ) -> None:
            if self.content_type is None:
                return
            for field_name, field in sender.fields.items():
                if not isinstance(field, ContentTypeField):
                    continue
                current_content_type = getattr(instance, field_name, None)
                if current_content_type is None and field.null:
                    continue
                if (
                    current_content_type is not None
                    and getattr(current_content_type, "pk", None) is not None
                ):
                    continue
                payload = {}
                if current_content_type is not None and hasattr(
                    current_content_type, "extract_db_fields"
                ):
                    payload = current_content_type.extract_db_fields()

                payload["name"] = sender.__name__
                content_type_obj = await self.content_type.query.create(**payload)
                setattr(instance, field_name, content_type_obj)

        model_class.signals.pre_save.connect(ensure_content_type)
        self._content_type_models_bound.add(model_class.__name__)

    @property
    def metadata(self) -> Any:
        for model_class in self.models.values():
            model_class.build(schema=self.db_schema)
        return self._metadata

    @metadata.setter
    def metadata(self, value: sqlalchemy.MetaData) -> None:
        self._metadata = value

    @cached_property
    def declarative_base(self) -> Any:
        if self.db_schema:
            metadata = sqlalchemy.MetaData(schema=self.db_schema)
        else:
            metadata = sqlalchemy.MetaData()
        return sa_declarative_base(metadata=metadata)

    @property
    def engine(self) -> AsyncEngine:
        assert self.database.engine, "database not started, no engine found."
        return self.database.engine

    @property
    def sync_engine(self) -> Engine:
        return self.engine.sync_engine

    async def create_all(self) -> None:
        self._attach_content_type_to_registered_models()
        if self.db_schema:
            await self.schema.create_schema(self.db_schema, True)
        async with Database(self.database, force_rollback=False) as database:  # noqa: SIM117
            async with database.transaction():
                await database.create_all(self.metadata)

    async def drop_all(self) -> None:
        if self.db_schema:
            await self.schema.drop_schema(self.db_schema, True, True)
        async with Database(self.database, force_rollback=False) as database:  # noqa: SIM117
            async with database.transaction():
                await database.drop_all(self.metadata)

    def _iter_databases(self) -> list[tuple[str | None, Database]]:
        databases: list[tuple[str | None, Database]] = [(None, self.database)]
        for name, db in self.extra.items():
            databases.append((name, db))
        return databases

    def get_model(
        self,
        model_name: str,
        *,
        include_content_type_attr: bool = True,
        include_reflected: bool = True,
        include_pattern: bool = False,
    ) -> Any:
        if (
            include_content_type_attr
            and model_name == "ContentType"
            and self.content_type is not None
        ):
            return self.content_type
        if model_name in self.models:
            return self.models[model_name]
        if include_reflected and model_name in self.reflected:
            return self.reflected[model_name]
        if include_pattern and model_name in self.pattern_models:
            return self.pattern_models[model_name]
        raise LookupError(f"Registry doesn't have a {model_name} model.")

    async def reflect_pattern_models(
        self,
        *,
        database_name: str | None = None,
        database: Database | None = None,
    ) -> None:
        if not self.pattern_models:
            return
        if database_name in self._pattern_reflected_dbs:
            return

        target_db = database
        if target_db is None:
            target_db = self.database if database_name is None else self.extra[database_name]

        schemes: set[None | str] = set()
        patterns = []
        for pattern_model in self.pattern_models.values():
            meta = pattern_model.meta
            if database_name not in meta.databases:
                continue
            schemes.update(meta.schemes)
            patterns.append(pattern_model)

        if not patterns:
            self._pattern_reflected_dbs.add(database_name)
            return

        tmp_metadata = sqlalchemy.MetaData()
        for schema in schemes:
            await target_db.run_sync(self._reflect_schema_metadata, tmp_metadata, schema)

        for table in tmp_metadata.tables.values():
            for pattern_model in patterns:
                meta = pattern_model.meta
                if table.schema not in meta.schemes:
                    continue
                if not meta.include_pattern.match(table.name):
                    continue
                if meta.exclude_pattern and meta.exclude_pattern.match(table.name):
                    continue
                if pattern_model.fields_not_supported_by_table(table):
                    continue

                model_name = meta.template(table)
                try:
                    self.get_model(model_name, include_pattern=False)
                except LookupError:
                    ...
                else:
                    raise RuntimeError(
                        f"Conflicting reflected model name generated: {model_name!r}."
                    )

                pattern_model.create_reflected_model(
                    table=table,
                    registry=self,
                    database=target_db,
                    name=model_name,
                )

        self._pattern_reflected_dbs.add(database_name)

    @staticmethod
    def _reflect_schema_metadata(
        connection: Any,
        metadata: sqlalchemy.MetaData,
        schema: str | None,
    ) -> None:
        inspector = sqlalchemy.inspect(connection)
        table_names = inspector.get_table_names(schema=schema)
        for table_name in table_names:
            try:
                sqlalchemy.Table(
                    table_name,
                    metadata,
                    schema=schema,
                    autoload_with=connection,
                )
            except NoSuchTableError:
                continue

    async def __aenter__(self) -> "Registry":
        connected: list[Database] = []
        try:
            for name, database in self._iter_databases():
                await database.connect()
                connected.append(database)
                await self.reflect_pattern_models(database_name=name, database=database)
        except Exception:
            for database in reversed(connected):
                if database.is_connected:
                    await database.disconnect()
            raise
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        for _, database in reversed(self._iter_databases()):
            if database.is_connected:
                await database.disconnect()
