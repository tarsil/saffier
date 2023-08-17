from typing import Any, Dict

from saffier.core.connection.database import Database
from saffier.core.connection.registry import Registry


class TenantRegistry(Registry):
    def __init__(self, database: Database, **kwargs: Any) -> None:
        super().__init__(database, **kwargs)
        self.tenant_models: Dict[str, Any] = {}
