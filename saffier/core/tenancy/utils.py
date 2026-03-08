from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING

from saffier.contrib.multi_tenancy.exceptions import ModelSchemaError
from saffier.contrib.multi_tenancy.utils import create_tables, table_schema
from saffier.core.terminal import Terminal

logger = logging.getLogger(__name__)
terminal = Terminal()

if TYPE_CHECKING:
    from saffier import Model, Registry
    from saffier.core.db.models.types import BaseModelType


async def create_schema(
    registry: Registry,
    schema_name: str,
    models: dict[str, type[BaseModelType]] | None = None,
    if_not_exists: bool = False,
    should_create_tables: bool = False,
) -> None:
    default_schema_name = registry.schema.get_default_schema() or "public"
    if schema_name.lower() == default_schema_name.lower():
        raise ModelSchemaError(
            f"Cannot create a schema with the same name as the default: '{schema_name}'."
        )

    await registry.schema.create_schema(schema_name, if_not_exists=if_not_exists)

    if should_create_tables:
        terminal.write_info(f"Creating the tables in schema: {schema_name}")
        await create_tables(registry, models or registry.models, schema_name)


def legacy_table_schema(model_class: type[Model], schema: str):  # type: ignore[valid-type]
    warnings.warn(
        "'table_schema' has been deprecated, use '<model>.table_schema' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return model_class.table_schema(schema)


__all__ = ["create_schema", "create_tables", "legacy_table_schema", "table_schema"]
