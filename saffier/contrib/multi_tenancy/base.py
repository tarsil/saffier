from typing import Any, ClassVar

from saffier.contrib.multi_tenancy.metaclasses import BaseTenantMeta, TenantMeta
from saffier.core.db.models import Model


class TenantModel(Model, metaclass=BaseTenantMeta):
    """
    Base for a multi-tenant model from the Saffier contrib.
    This is **not mandatory** and can be used as a possible
    out of the box solution for multi tenancy.

    This design is not meant to be "the one" but instead an
    example of how to achieve the multi-tenancy in a simple fashion
    using Saffier models.
    """

    meta: ClassVar[TenantMeta] = TenantMeta(None)

    @classmethod
    def real_add_to_registry(cls, **kwargs: Any) -> type[Model]:
        result = super().real_add_to_registry(**kwargs)

        registry = getattr(result.meta, "registry", None)
        if (
            registry
            and result.meta.is_tenant
            and not result.meta.abstract
            and not result.is_proxy_model
        ):
            if result.meta.register_default is False:
                registry.models.pop(result.__name__, None)
            registry.tenant_models[result.__name__] = result

        return result
