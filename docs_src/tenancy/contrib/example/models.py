import saffier
from saffier.contrib.multi_tenancy import TenantModel, TenantRegistry
from saffier.contrib.multi_tenancy.models import DomainMixin, TenantMixin, TenantUserMixin

database = saffier.Database("<YOUR-CONNECTION-STRING>")
registry = TenantRegistry(database=database)


class Tenant(TenantMixin):
    """
    Inherits all the fields from the `TenantMixin`.
    """

    class Meta:
        registry = registry


class Domain(DomainMixin):
    """
    Inherits all the fields from the `DomainMixin`.
    """

    class Meta:
        registry = registry


class TenantUser(TenantUserMixin):
    """
    Inherits all the fields from the `TenantUserMixin`.
    """

    class Meta:
        registry = registry


class User(TenantModel):
    """
    The model responsible for users across all schemas.
    What we can also refer as a `system user`.

    We don't want this table to be across all new schemas
    created, just the default (or shared) so `is_tenant = False`
    needs to be set.
    """

    name = saffier.CharField(max_length=255)
    email = saffier.EmailField(max_length=255)

    class Meta:
        registry = registry
        is_tenant = False


class HubUser(User):
    """
    This is a schema level type of user.
    This model it is the one that will be used
    on a `schema` level type of user.

    Very useful we want to have multi-tenancy applications
    where each user has specific accesses.
    """

    name = saffier.CharField(max_length=255)
    email = saffier.EmailField(max_length=255)

    class Meta:
        registry = registry
        is_tenant = True


class Item(TenantModel):
    """
    General item that should be across all
    the schemas and public inclusively.
    """

    sku = saffier.CharField(max_length=255)

    class Meta:
        registry = registry
        is_tenant = True
