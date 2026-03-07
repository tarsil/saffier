from __future__ import annotations

import os
import re
from functools import cached_property
from pathlib import Path
from typing import Any, ClassVar

from saffier.conf.base import BaseSettings, SettingsExtensionDefinition


class SaffierSettings(BaseSettings):
    ipython_args: list[str] = ["--no-banner"]
    ptpython_config_file: str = "~/.config/ptpython/config.py"

    file_upload_temp_dir: str | os.PathLike[str] | None = None
    file_upload_permissions: int | None = 0o644
    file_upload_directory_permissions: int | None = None
    media_root: str | os.PathLike[str] = Path("media")
    media_url: str = ""
    storages: dict[str, dict[str, object]] = {
        "default": {
            "backend": "saffier.core.files.storage.filesystem.FileSystemStorage",
        }
    }

    use_tz: bool = True
    preloads: list[str] | tuple[str, ...] = ()
    extensions: list[SettingsExtensionDefinition] | tuple[SettingsExtensionDefinition, ...] = ()
    allow_automigrations: bool = True
    multi_schema: bool | re.Pattern[str] | str = False
    ignore_schema_pattern: re.Pattern[str] | str | None = "information_schema"
    migrate_databases: list[str | None] | tuple[str | None, ...] = (None,)
    migration_directory: str | os.PathLike[str] = Path("migrations")
    alembic_ctx_kwargs: dict[str, Any] = {
        "compare_type": True,
        "render_as_batch": True,
    }

    # Dialects
    postgres_dialects: ClassVar[set[str]] = {"postgres", "postgresql"}
    mysql_dialects: ClassVar[set[str]] = {"mysql"}
    sqlite_dialects: ClassVar[set[str]] = {"sqlite"}
    mssql_dialects: ClassVar[set[str]] = {"mssql"}

    # Drivers
    postgres_drivers: ClassVar[set[str]] = {"aiopg", "asyncpg"}
    mysql_drivers: ClassVar[set[str]] = {"aiomysql", "asyncmy"}
    sqlite_drivers: ClassVar[set[str]] = {"aiosqlite"}

    default_related_lookup_field: str = "id"
    orm_concurrency_enabled: bool = True
    orm_concurrency_limit: int | None = None
    filter_operators: ClassVar[dict[str, str]] = {
        "exact": "__eq__",
        "iexact": "ilike",
        "contains": "like",
        "icontains": "ilike",
        "in": "in_",
        "gt": "__gt__",
        "gte": "__ge__",
        "lt": "__lt__",
        "lte": "__le__",
        "isnull": "isnull",
    }
    many_to_many_relation: str = "relation_{key}"

    @property
    def mssql_drivers(self) -> set[str]:
        """
        SQLAlchemy does not expose async MSSQL support beyond aioodbc.
        """
        return {"aioodbc"}

    @cached_property
    def admin_config(self) -> Any:
        from saffier.contrib.admin.config import AdminConfig

        return AdminConfig()


__all__ = ["SaffierSettings"]
