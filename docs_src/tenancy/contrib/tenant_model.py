import saffier
from saffier.contrib.multi_tenancy import TenantModel, TenantRegistry

database = saffier.Database("<YOUR-CONNECTION-STRING>")
registry = TenantRegistry(database=database)


class User(TenantModel):
    """
    A `users` table that should be created in the `shared` schema
    (or public) and in the subsequent new schemas.
    """

    name = saffier.CharField(max_length=255)
    email = saffier.CharField(max_length=255)

    class Meta:
        registry = registry
        is_tenant = True
