import inspect
import logging
import sys
from collections.abc import Callable, Generator
from typing import Any

import sqlalchemy
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql import schema, sqltypes

import saffier
from saffier import Database, Registry
from saffier.core.sync import execsync
from saffier.core.terminal import Print

printer = Print()
logger = logging.getLogger(__name__)

SQL_GENERIC_TYPES = {
    sqltypes.BigInteger: saffier.BigIntegerField,
    sqltypes.Integer: saffier.IntegerField,
    sqltypes.JSON: saffier.JSONField,
    sqltypes.Date: saffier.DateField,
    sqltypes.String: saffier.CharField,
    sqltypes.Unicode: saffier.CharField,
    sqltypes.BINARY: saffier.CharField,
    sqltypes.Boolean: saffier.BooleanField,
    sqltypes.Enum: saffier.ChoiceField,
    sqltypes.DateTime: saffier.DateTimeField,
    sqltypes.Numeric: saffier.DecimalField,
    sqltypes.Float: saffier.FloatField,
    sqltypes.Double: saffier.FloatField,
    sqltypes.SmallInteger: saffier.IntegerField,
    sqltypes.Text: saffier.TextField,
    sqltypes.Time: saffier.TimeField,
    sqltypes.Uuid: saffier.UUIDField,
}

DB_MODULE = "saffier"


def func_accepts_kwargs(func: Callable) -> bool:
    """Return whether a callable accepts arbitrary keyword arguments.

    Signal receivers and other extensibility hooks in Saffier commonly require
    `**kwargs` support so new payload values can be introduced without breaking
    existing call sites.

    Args:
        func (Callable): Callable object to inspect.

    Returns:
        bool: `True` when `func` defines a `**kwargs` parameter.
    """
    return any(
        param
        for param in inspect.signature(func).parameters.values()
        if param.kind == param.VAR_KEYWORD
    )


class InspectDB:
    """Reflect an existing database and emit Saffier model definitions.

    The inspector is the engine behind the `saffier inspectdb` command. It
    reflects database metadata, translates SQLAlchemy types into Saffier fields,
    and prints a starter module built from `ReflectModel` classes.
    """

    def __init__(self, database: str, schema: str | None) -> None:
        """Store the database URL and schema targeted for reflection.

        Args:
            database (str): Database URL passed to `Database`.
            schema (str | None): Optional schema name restricting reflection to
                one namespace.
        """
        self._database = database
        self._schema = schema

    @property
    def database(self) -> Database:
        """Build a `Database` instance for the configured URL."""
        return Database(self._database)

    @property
    def schema(self) -> str | None:
        """Return the schema requested for reflection, if any."""
        return self._schema

    def inspect(self) -> None:
        """Run the full reflection workflow and stream generated code to stdout.

        The generated output is intentionally starter code: it mirrors the
        current database structure using `ReflectModel` definitions so users can
        review, edit, and integrate the result into their applications.
        """
        registry = Registry(database=self.database)
        metadata = execsync(self._collect_metadata)(registry=registry)

        # Generate the tables
        tables, _ = self.generate_table_information(metadata)

        for line in self.write_output(tables, self.database.url._url):
            sys.stdout.writelines(line)  # type: ignore

    async def _collect_metadata(self, registry: Registry) -> sqlalchemy.MetaData:
        """Connect to the database, reflect metadata, and disconnect cleanly.

        Args:
            registry (Registry): Temporary registry bound to the target
                database.

        Returns:
            sqlalchemy.MetaData: Reflected metadata object.
        """
        await registry.database.connect()
        try:
            engine: AsyncEngine = registry.engine
            metadata: sqlalchemy.MetaData = (
                sqlalchemy.MetaData(schema=self.schema)
                if self.schema is not None
                else sqlalchemy.MetaData()
            )
            return await self.reflect(engine=engine, metadata=metadata)
        finally:
            await registry.database.disconnect()

    def generate_table_information(
        self, metadata: sqlalchemy.MetaData
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Transform reflected metadata into code-generation payloads.

        Args:
            metadata: Reflected SQLAlchemy metadata.

        Returns:
            tuple[list[dict[str, Any]], dict[str, str]]: Table descriptors and a
            lookup from table name to generated class name.
        """
        tables_dict = dict(metadata.tables.items())
        tables = []
        models: dict[str, str] = {}
        for key, table in tables_dict.items():
            table_details: dict[str, Any] = {}
            table_details["tablename"] = key
            table_details["class_name"] = key.replace("_", "").capitalize()
            table_details["class"] = None
            table_details["table"] = table
            models[key] = key.replace("_", "").capitalize()

            # Get the details of the foreign key
            table_details["foreign_keys"] = self.get_foreign_keys(table)

            # Get the details of the indexes
            table_details["indexes"] = table.indexes
            table_details["constraints"] = table.constraints
            tables.append(table_details)

        return tables, models

    def get_foreign_keys(
        self, table_or_column: sqlalchemy.Table | sqlalchemy.Column
    ) -> list[dict[str, Any]]:
        """Extract normalized foreign-key metadata for reflection output.

        Args:
            table_or_column (sqlalchemy.Table | sqlalchemy.Column): Reflected
                table or column exposing `.foreign_keys`.

        Returns:
            list[dict[str, Any]]: Foreign-key descriptors used later when
            emitting field declarations.
        """
        details: list[dict[str, Any]] = []

        for foreign_key in table_or_column.foreign_keys:
            fk: dict[str, Any] = {}
            fk["column"] = foreign_key.column
            fk["column_name"] = foreign_key.column.name
            fk["tablename"] = foreign_key.column.table.name
            fk["class_name"] = foreign_key.column.table.name.replace("_", "").capitalize()
            fk["on_delete"] = foreign_key.ondelete
            fk["on_update"] = foreign_key.onupdate
            details.append(fk)

        return details

    def get_field_type(
        self, column: sqlalchemy.Column, is_fk: bool = False
    ) -> tuple[str, dict[str, Any]]:
        """Translate one reflected SQLAlchemy column into a Saffier field.

        Args:
            column (sqlalchemy.Column): Reflected column to inspect.
            is_fk (bool): Whether the column is being rendered as a relationship
                field instead of a scalar field.

        Returns:
            tuple[str, dict[str, Any]]: Field class name and keyword arguments to
            include in the generated model code.
        """
        if is_fk:
            return "ForeignKey" if not column.unique else "OneToOne", {}

        real_field: Any = column.type.as_generic()
        try:
            field_type = SQL_GENERIC_TYPES[type(real_field)].__name__
        except KeyError:
            logger.info(
                f"Unable to understand the field type for `{column.name}`, defaulting to TextField."
            )
            field_type = "TextField"

        field_params: dict[str, Any] = {}

        if field_type == "CharField":
            field_params["max_length"] = real_field.length

        if (
            field_type in {"CharField", "TextField"}
            and hasattr(real_field, "collation")
            and real_field.collation is not None
        ):
            field_params["collation"] = real_field.collation

        if field_type == "DecimalField":
            field_params["max_digits"] = real_field.precision
            field_params["decimal_places"] = real_field.scale

        if field_type == "BinaryField":
            field_params["sql_nullable"] = getattr(real_field, "none_as_null", False)

        return field_type, field_params

    def get_meta(
        self, table: dict[str, Any], unique_constraints: set[str], _indexes: set[str]
    ) -> list[str]:
        """Generate the `Meta` inner-class body for one reflected model.

        Args:
            table (dict[str, Any]): Reflected table descriptor assembled by
                `generate_table_information`.
            unique_constraints (set[str]): Column names already rendered as
                per-field unique constraints.
            _indexes (set[str]): Column names already rendered as per-field
                indexes.

        Returns:
            list[str]: Source lines composing the generated `Meta` class.
        """
        unique_together: list[saffier.UniqueConstraint] = []
        unique_indexes: list[saffier.Index] = []
        indexes = list(table["indexes"])
        constraints = list(table["constraints"])

        # Handle the unique together
        for constraint in constraints:
            if isinstance(constraint, schema.UniqueConstraint):
                columns = [
                    column.name
                    for column in constraint.columns
                    if column.name not in unique_constraints
                ]
                unique_definition = saffier.UniqueConstraint(fields=columns, name=constraint.name)
                unique_together.append(unique_definition)

        # Handle the indexes
        for index in indexes:
            if isinstance(index, schema.Index):
                columns = [column.name for column in index.columns if column.name not in _indexes]
                index_definition = saffier.Index(name=index.name, fields=columns)
                unique_indexes.append(index_definition)

        meta = [""]
        meta += [
            "    class Meta:\n",
            "        registry = registry\n",
            f"        tablename = '{table['tablename']}'\n",
        ]

        if unique_together:
            meta.append(
                f"        unique_together = {unique_together}\n",
            )

        if unique_indexes:
            meta.append(
                f"        indexes = {unique_indexes}\n",
            )
        return meta

    async def reflect(
        self, *, engine: sqlalchemy.Engine, metadata: sqlalchemy.MetaData
    ) -> sqlalchemy.MetaData:
        """Reflect database metadata through an async SQLAlchemy engine.

        Returns:
            sqlalchemy.MetaData: Reflected metadata object.
        """

        async with engine.connect() as connection:
            logger.info("Collecting database tables information...")
            await connection.run_sync(metadata.reflect)
        return metadata

    def write_output(self, tables: list[Any], connection_string: str) -> Generator[str]:
        """Yield the generated Python source for reflected models.

        Args:
            tables: Table descriptors produced by reflection.
            connection_string: Database connection string used in the generated
                file.
        """
        yield f"# This is an auto-generated Saffier model module. Saffier version `{saffier.__version__}`.\n"
        yield "#   * Rearrange models' order.\n"
        yield "#   * Make sure each model has one field with primary_key=True.\n"
        yield (
            "#   * Make sure each ForeignKey and OneToOne has `on_delete` set "
            "to the desired behavior.\n"
        )
        yield (
            "# Feel free to rename the models, but don't rename tablename values or field names.\n"
        )
        yield f"# The generated models do not manage migrations. Those are handled by `{DB_MODULE}.Model`.\n"
        yield f"# The automatic generated models will be subclassed as `{DB_MODULE}.ReflectModel`.\n\n\n"
        yield f"import {DB_MODULE} \n"
        yield f"from {DB_MODULE} import UniqueConstraint, Index \n"

        yield "\n"
        yield "\n"
        yield f"database = {DB_MODULE}.Database('{connection_string}')\n"
        yield f"registry = {DB_MODULE}.Registry(database=database)\n"

        # Start writing the classes
        for table in tables:
            unique_constraints: set[str] = set()
            indexes: set[str] = set()

            yield "\n"
            yield "\n"
            yield "\n"
            yield "class {}({}.ReflectModel):\n".format(table["class_name"], DB_MODULE)
            # yield "    ...\n"

            sqla_table: sqlalchemy.Table = table["table"]
            columns = list(sqla_table.columns)

            # Get the column information
            for column in columns:
                # ForeignKey related
                foreign_keys = self.get_foreign_keys(column)
                is_fk = bool(foreign_keys)
                attr_name = column.name

                field_type, field_params = self.get_field_type(column, is_fk)
                field_params["null"] = column.nullable

                if column.primary_key:
                    field_params["primary_key"] = column.primary_key
                    unique_constraints.add(attr_name)
                if column.unique:
                    unique_constraints.add(attr_name)
                if column.unique and not column.primary_key:
                    field_params["unique"] = column.unique

                if column.index:
                    field_params["index"] = column.index
                    indexes.add(column.name)

                if column.comment:
                    field_params["comment"] = column.comment
                if column.default:
                    field_params["default"] = column.default

                if is_fk:
                    field_params["to"] = foreign_keys[0]["class_name"]
                    field_params["on_update"] = foreign_keys[0]["on_update"]
                    field_params["on_delete"] = foreign_keys[0]["on_update"]
                    field_params["related_name"] = "{}_{}_set".format(
                        attr_name.lower(),
                        field_params["to"].lower(),
                    )

                field_type += "("
                field_description = "{} = {}{}".format(
                    attr_name,
                    "" if "." in field_type else f"{DB_MODULE}.",
                    field_type,
                )
                if field_params:
                    if not field_description.endswith("("):
                        field_description += ", "
                    field_description += ", ".join(f"{k}={v!r}" for k, v in field_params.items())
                field_description += ")\n"
                yield f"    {field_description}"

            yield "\n"
            yield from self.get_meta(table, unique_constraints, indexes)
