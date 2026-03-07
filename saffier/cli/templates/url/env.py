# Default env template

import asyncio
import logging
import os
from collections.abc import Generator
from logging.config import fileConfig
from typing import TYPE_CHECKING, Any, Literal

from alembic import context
from rich.console import Console

import saffier
from saffier.core.connection.database import Database
from saffier.core.connection.registry import Registry

if TYPE_CHECKING:
    import sqlalchemy

console = Console()
config: Any = context.config

fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")
MAIN_DATABASE_NAME: str = " "


def iter_databases(
    registry: Registry,
) -> Generator[tuple[str | None, Database, "sqlalchemy.MetaData"], None, None]:
    url: str | None = os.environ.get("SAFFIER_DATABASE_URL")
    name: str | Literal[False] | None = os.environ.get("SAFFIER_DATABASE") or False
    if url and not name:
        try:
            name = registry.metadata_by_url.get_name(url)
        except KeyError:
            name = None

    if name is False:
        for name in saffier.monkay.settings.migrate_databases:
            if name is None:
                yield (None, registry.database, registry.metadata_by_name[None])
            else:
                yield (name, registry.extra[name], registry.metadata_by_name[name])
    else:
        if name == MAIN_DATABASE_NAME:
            name = None

        if url:
            database = Database(url)
        elif name is None:
            database = registry.database
        else:
            database = registry.extra[name]

        yield (name, database, registry.metadata_by_name[name])


def run_migrations_offline() -> Any:
    registry = saffier.get_migration_prepared_registry()
    for name, db, metadata in iter_databases(registry):
        context.configure(
            url=str(db.url),
            target_metadata=metadata,
            literal_binds=True,
            **saffier.monkay.settings.alembic_ctx_kwargs,
        )

        with context.begin_transaction():
            context.run_migrations(engine_name=name or "")


def do_run_migrations(connection: Any, name: str | None, metadata: "sqlalchemy.MetaData") -> Any:
    def process_revision_directives(context, revision, directives) -> Any:  # type: ignore
        if getattr(config.cmd_opts, "autogenerate", False):
            script = directives[0]
            empty = True
            for upgrade_ops in script.upgrade_ops_list:
                if not upgrade_ops.is_empty():
                    empty = False
                    break
            if empty:
                directives[:] = []
                console.print("[bright_red]No changes in schema detected.")

    context.configure(
        connection=connection,
        target_metadata=metadata,
        upgrade_token=f"{name or ''}_upgrades",
        downgrade_token=f"{name or ''}_downgrades",
        process_revision_directives=process_revision_directives,
        **saffier.monkay.settings.alembic_ctx_kwargs,
    )

    with context.begin_transaction():
        context.run_migrations(engine_name=name or "")


async def run_migrations_online() -> Any:
    registry = saffier.get_migration_prepared_registry()
    async with registry:
        for name, db, metadata in iter_databases(registry):
            async with db as database:
                await database.run_sync(do_run_migrations, name, metadata)


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
