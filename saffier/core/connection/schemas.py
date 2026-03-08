from collections.abc import Sequence
from typing import TYPE_CHECKING

import sqlalchemy
from sqlalchemy.exc import DBAPIError, ProgrammingError

from saffier.exceptions import SchemaError

if TYPE_CHECKING:
    from saffier import Registry
    from saffier.core.connection.database import Database


class Schema:
    """Schema management helper bound to a registry.

    The object centralizes low-level schema creation, teardown, and schema-path
    switching so the registry can reuse the same logic for migrations, tenancy,
    and table-creation helpers.
    """

    def __init__(self, registry: type["Registry"]) -> None:
        self.registry = registry

    @property
    def database(self) -> "Database":
        return self.registry.database

    def get_default_schema(self) -> str | None:
        """Return the database dialect's default schema name.

        Returns:
            str | None: Default schema reported by the active dialect.
        """
        if not hasattr(self, "_default_schema"):
            self._default_schema = self.database.url.sqla_url.get_dialect(True).default_schema_name
        return self._default_schema

    async def activate_schema_path(
        self, database: "Database", schema: str, is_shared: bool = True
    ) -> None:
        path = (
            f"SET search_path TO {schema}, shared;"
            if is_shared
            else f"SET search_path TO {schema};"
        )
        expression = sqlalchemy.text(path)
        await database.execute(expression)

    async def create_schema(
        self,
        schema: str | None,
        if_not_exists: bool = False,
        init_models: bool = False,
        init_tenant_models: bool = False,
        update_cache: bool = True,
        databases: Sequence[str | None] = (None,),
    ) -> None:
        """Create a schema and optionally create model tables inside it.

        Args:
            schema: Schema name to create. `None` means "create tables in the
                default database namespace only".
            if_not_exists: Whether schema and table creation should be
                idempotent.
            init_models: Whether registered model tables should be created after
                the schema exists.
            init_tenant_models: Reserved for backward compatibility.
            update_cache: Whether schema-specific table caches should be
                refreshed when building tables.
            databases: Database aliases that should receive the operation.
        """
        del init_tenant_models
        schema_tables_by_metadata: dict[sqlalchemy.MetaData, list[sqlalchemy.Table]] = {}

        if init_models:
            for collection_name in ("models", "reflected"):
                for model_class in getattr(self.registry, collection_name, {}).values():
                    if getattr(model_class, "__using_schema__", None) is not None:
                        continue
                    table = model_class.table_schema(schema=schema, update_cache=update_cache)
                    schema_tables_by_metadata.setdefault(table.metadata, []).append(table)

        for database_name in databases:
            database = (
                self.registry.database
                if database_name is None
                else self.registry.extra[database_name]
            )
            async with database as database:
                with database.force_rollback(False):
                    if schema is None:
                        metadata = self.registry.metadata_by_name[database_name]

                        def execute_create_all(
                            connection: sqlalchemy.Connection,
                            metadata: sqlalchemy.MetaData = metadata,
                        ) -> None:
                            metadata.create_all(connection, checkfirst=if_not_exists)

                        await database.run_sync(execute_create_all)
                        continue

                    try:
                        await database.run_sync(
                            self._execute_create_schema,
                            schema,
                            if_not_exists,
                            schema_tables_by_metadata,
                            init_models,
                        )
                    except ProgrammingError as e:
                        raise SchemaError(detail=e.orig.args[0]) from e  # type: ignore[index]

    async def drop_schema(
        self,
        schema: str | None,
        cascade: bool = False,
        if_exists: bool = False,
        databases: Sequence[str | None] = (None,),
    ) -> None:
        """Drop a schema or all tables from the selected databases.

        Args:
            schema: Schema name to drop, or `None` to drop tables from the
                default namespace.
            cascade: Whether the schema drop should cascade.
            if_exists: Whether missing schema/table objects should be ignored.
            databases: Database aliases that should receive the operation.
        """

        for database_name in databases:
            database = (
                self.registry.database
                if database_name is None
                else self.registry.extra[database_name]
            )
            async with database as database:
                with database.force_rollback(False):
                    try:
                        await database.run_sync(
                            self._execute_drop_schema,
                            database_name,
                            schema,
                            cascade,
                            if_exists,
                        )
                    except DBAPIError as e:
                        raise SchemaError(detail=e.orig.args[0]) from e  # type: ignore[index]

    def _execute_create_schema(
        self,
        connection: sqlalchemy.Connection,
        schema: str,
        if_not_exists: bool,
        schema_tables_by_metadata: dict[sqlalchemy.MetaData, list[sqlalchemy.Table]],
        init_models: bool,
    ) -> None:
        connection.execute(
            sqlalchemy.schema.CreateSchema(
                name=schema,
                if_not_exists=if_not_exists,
            )
        )
        if init_models:
            for metadata, tables in schema_tables_by_metadata.items():
                metadata.create_all(
                    connection,
                    checkfirst=if_not_exists,
                    tables=list(tables),
                )

    def _execute_drop_schema(
        self,
        connection: sqlalchemy.Connection,
        database_name: str | None,
        schema: str | None,
        cascade: bool,
        if_exists: bool,
    ) -> None:
        if schema is not None:
            connection.execute(
                sqlalchemy.schema.DropSchema(
                    name=schema,
                    cascade=cascade,
                    if_exists=if_exists,
                )
            )
            return
        self.registry.metadata_by_name[database_name].drop_all(
            connection,
            checkfirst=if_exists,
        )
