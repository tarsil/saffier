import os
from dataclasses import dataclass
from typing import Any, Optional

from saffier.conf.global_settings import SaffierSettings


@dataclass
class TenancySettings(SaffierSettings):
    """
    BaseSettings used for the contrib of Saffier tenancy
    """

    auto_create_schema: bool = True
    auto_drop_schema: bool = False
    tenant_schema_default: str = "public"
    tenant_model: Optional[str] = None
    domain: Any = os.getenv("DOMAIN")
    domain_name: str = "localhost"
    auth_user_model: Optional[str] = None
