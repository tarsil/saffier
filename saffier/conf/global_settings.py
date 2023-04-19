from functools import cached_property
from typing import List, Optional

from pydantic import BaseConfig, BaseSettings

from saffier.conf.enums import EnvironmentType


class SaffierSettings(BaseSettings):
    debug: bool = False
    environment: Optional[str] = EnvironmentType.PRODUCTION
    ipython_args: List[str] = []
    notebook_args: List[str] = []

    class Config(BaseConfig):
        extra = "allow"
        keep_untouched = (cached_property,)
