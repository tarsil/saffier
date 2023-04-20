from functools import cached_property
from typing import List, Optional

from pydantic import BaseConfig, BaseSettings

from saffier.conf.enums import EnvironmentType


class SaffierSettings(BaseSettings):
    debug: bool = False
    environment: Optional[str] = EnvironmentType.PRODUCTION
    ipython_args: List[str] = ["--no-banner"]
    ptpython_config_file: str = "~/.config/ptpython/config.py"

    class Config(BaseConfig):
        extra = "allow"
        keep_untouched = (cached_property,)
