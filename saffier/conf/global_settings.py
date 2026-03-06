from dataclasses import dataclass
from typing import ClassVar

from dymmond_settings import Settings


@dataclass
class SaffierSettings(Settings):
    ipython_args: ClassVar[list[str]] = ["--no-banner"]
    ptpython_config_file: str = "~/.config/ptpython/config.py"

    # Dialects
    postgres_dialects: ClassVar[set[str]] = {"postgres", "postgresql"}
    mysql_dialects: ClassVar[set[str]] = {"mysql"}
    sqlite_dialects: ClassVar[set[str]] = {"sqlite"}
    mssql_dialects: ClassVar[set[str]] = {"mssql"}

    # Drivers
    postgres_drivers: ClassVar[set[str]] = {"aiopg", "asyncpg"}
    mysql_drivers: ClassVar[set[str]] = {"aiomysql", "asyncmy"}
    sqlite_drivers: ClassVar[set[str]] = {"aiosqlite"}

    @property
    def mssql_drivers(self) -> set[str]:
        """
        Do not override this one as SQLAlchemy doesn't support async for MSSQL.
        """
        return {"aioodbc"}

    # General settings
    default_related_lookup_field: str = "id"
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
    }

    many_to_many_relation: str = "relation_{key}"
