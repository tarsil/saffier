from functools import cached_property
from typing import List, Set

from pydantic import BaseConfig, BaseSettings


class SaffierSettings(BaseSettings):
    ipython_args: List[str] = ["--no-banner"]
    ptpython_config_file: str = "~/.config/ptpython/config.py"

    # Dialects
    postgres_dialects: Set[str] = {"postgres", "postgresql"}
    mysql_dialects: Set[str] = {"mysql"}
    sqlite_dialects: Set[str] = {"sqlite"}
    mssql_dialects: Set[str] = {"mssql"}

    # Drivers
    postgres_drivers = {"aiopg", "asyncpg"}
    mysql_drivers = {"aiomysql", "asyncmy"}
    sqlite_drivers = {"aiosqlite"}

    @property
    def mssql_drivers(self) -> Set[str]:
        """
        Do not override this one as SQLAlchemy doesn't support async for MSSQL.
        """
        return {"aioodbc"}

    class Config(BaseConfig):
        extra = "allow"
        keep_untouched = (cached_property,)
