from functools import cached_property
from typing import List, Optional, Set

from pydantic import BaseConfig, BaseSettings

from saffier.conf.enums import EnvironmentType


class SaffierSettings(BaseSettings):
    debug: bool = False
    environment: Optional[str] = EnvironmentType.PRODUCTION
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
    mssql_drivers = {"aioodbc"}

    class Config(BaseConfig):
        extra = "allow"
        keep_untouched = (cached_property,)
