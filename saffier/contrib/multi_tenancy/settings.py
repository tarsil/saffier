import os
from functools import cached_property
from typing import Any, Optional

from pydantic_settings import SettingsConfigDict

from saffier.conf.global_settings import SaffierSettings


class TenancySettings(SaffierSettings):
    """
    BaseSettings used for the contrib of Saffier tenancy
    """

    model_config = SettingsConfigDict(extra="allow", ignored_types=(cached_property,))
    auto_create_schema: bool = True
    auto_drop_schema: bool = False
    tenant_schema_default: str = "public"
    tenant_model: Optional[str] = None
    domain: Any = os.getenv("DOMAIN")
    domain_name: str = "localhost"
    auth_user_model: Optional[str] = None
