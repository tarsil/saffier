from dataclasses import dataclass
from typing import ClassVar, Dict, List, Set

from dymmond_settings import Settings


@dataclass
class SaffierSettings(Settings):
    ipython_args: ClassVar[List[str]] = ["--no-banner"]
    ptpython_config_file: str = "~/.config/ptpython/config.py"

    # Dialects
    postgres_dialects: ClassVar[Set[str]] = {"postgres", "postgresql"}
    mysql_dialects: ClassVar[Set[str]] = {"mysql"}
    sqlite_dialects: ClassVar[Set[str]] = {"sqlite"}
    mssql_dialects: ClassVar[Set[str]] = {"mssql"}

    # Drivers
    postgres_drivers: ClassVar[Set[str]] = {"aiopg", "asyncpg"}
    mysql_drivers: ClassVar[Set[str]] = {"aiomysql", "asyncmy"}
    sqlite_drivers: ClassVar[Set[str]] = {"aiosqlite"}

    @property
    def mssql_drivers(self) -> Set[str]:
        """
        Do not override this one as SQLAlchemy doesn't support async for MSSQL.
        """
        return {"aioodbc"}

    # General settings
    default_related_lookup_field: str = "id"
    filter_operators: ClassVar[Dict[str, str]] = {
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
