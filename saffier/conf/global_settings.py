from functools import cached_property
from typing import List, Optional

from pydantic import BaseConfig, BaseSettings

from saffier.conf.enums import EnvironmentType


class SaffierSettings(BaseSettings):
    debug: bool = False
    environment: Optional[str] = EnvironmentType.PRODUCTION
    ipython_args: List[str] = ["--no-banner"]
    ptpython_config_file: str = "~/.config/ptpython/config.py"

    @property
    def postgres_dialects(self):
        """A list of postgres dialect representations"""
        return {"postgres", "postgresql"}

    @property
    def mysql_dialects(self):
        """A list of mysql dialect representations"""
        return {"mysql"}

    @property
    def sqlite_dialects(self):
        """A list of sqlite dialect representations"""
        return {"sqlite"}

    @property
    def mssql_dialects(self):
        """A list of mssql dialect representations"""
        return {"mssql"}

    class Config(BaseConfig):
        extra = "allow"
        keep_untouched = (cached_property,)
