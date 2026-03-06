import logging
from typing import TYPE_CHECKING

import sqlalchemy

from saffier.core.terminal import Terminal

terminal = Terminal()
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from saffier.contrib.multi_tenancy import TenantModel, TenantRegistry


_SCHEMA_TABLE_CACHE: dict[tuple[int, str], dict[str, sqlalchemy.Table]] = {}


def _build_schema_tables(
    registry: "TenantRegistry", schema: str, target_model: type["TenantModel"]
) -> dict[str, sqlalchemy.Table]:
    metadata = sqlalchemy.MetaData(schema=schema)
    schema_tables: dict[str, sqlalchemy.Table] = {}

    for model in registry.tenant_models.values():
        schema_tables[model.table.name] = model.table.to_metadata(metadata, schema=schema)

    # Ensure non-registered tenant models still get a table clone for this schema.
    schema_tables.setdefault(
        target_model.table.name,
        target_model.table.to_metadata(metadata, schema=schema),
    )
    return schema_tables


def table_schema(model_class: type["TenantModel"], schema: str) -> sqlalchemy.Table:
    """
    Making sure the tables on inheritance state, creates the new
    one properly.

    The use of context vars instead of using the lru_cache comes from
    a warning from `ruff` where lru can lead to memory leaks.
    """
    cache_key = (id(model_class.meta.registry), schema)
    if cache_key not in _SCHEMA_TABLE_CACHE:
        _SCHEMA_TABLE_CACHE[cache_key] = _build_schema_tables(
            registry=model_class.meta.registry,
            schema=schema,
            target_model=model_class,
        )

    table_name = model_class.table.name
    cached_tables = _SCHEMA_TABLE_CACHE[cache_key]
    if table_name not in cached_tables:
        _SCHEMA_TABLE_CACHE[cache_key] = _build_schema_tables(
            registry=model_class.meta.registry,
            schema=schema,
            target_model=model_class,
        )
        cached_tables = _SCHEMA_TABLE_CACHE[cache_key]

    return cached_tables[table_name]


async def create_tables(
    registry: "TenantRegistry", tenant_models: dict[str, type["TenantModel"]], schema: str
) -> None:
    """
    Creates the table models for a specific schema just generated.

    Iterates through the tenant models and creates them in the schema.
    """

    metadata = sqlalchemy.MetaData(schema=schema)

    for name, model in tenant_models.items():
        logger.info(f"Creating table '{name}' for schema: '{schema}'")
        model.table.to_metadata(metadata, schema=schema)

    try:
        async with registry.engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
    except Exception as e:
        logger.error(str(e))
    finally:
        await registry.engine.dispose()
