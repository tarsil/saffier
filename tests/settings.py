import os

from saffier.contrib.multi_tenancy.settings import TenancySettings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/saffier"
)
DATABASE_ALTERNATIVE_URL = os.environ.get(
    "TEST_DATABASE_ALTERNATIVE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/edgy_alt",
)
TEST_DATABASE = "postgresql+asyncpg://postgres:postgres@localhost:5432/test_saffier"


class TestSettings(TenancySettings):
    tenant_model: str = "Tenant"
    auth_user_model: str = "User"
