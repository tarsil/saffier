from saffier.contrib.multi_tenancy.settings import TenancySettings


class SaffierSettings(TenancySettings):
    tenant_model: str = "Tenant"
    """
    The Tenant model created
    """
    auth_user_model: str = "User"
    """
    The `user` table created. Not the `HubUser`!
    """
