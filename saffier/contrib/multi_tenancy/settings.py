import os
from typing import Any

from saffier.conf.global_settings import SaffierSettings


class TenancySettings(SaffierSettings):
    """Default settings consumed by Saffier's multi-tenancy contrib package.

    These options control schema bootstrap behavior, the default tenant schema,
    and model references used by tenant-aware helpers. Applications can inherit
    from this settings object or override individual attributes through their
    normal Saffier settings configuration.
    """

    auto_create_schema: bool = True
    auto_drop_schema: bool = False
    tenant_schema_default: str = "public"
    tenant_model: str | None = None
    domain: Any = os.getenv("DOMAIN")
    domain_name: str = "localhost"
    auth_user_model: str | None = None
