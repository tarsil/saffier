import saffier
from saffier.contrib.multi_tenancy import TenantRegistry
from saffier.contrib.multi_tenancy.models import TenantMixin

database = saffier.Database("<YOUR-CONNECTION-STRING>")
registry = TenantRegistry(database=database)


class Tenant(TenantMixin):
    """
    Inherits all the fields from the `TenantMixin`.
    """

    class Meta:
        registry = registry
