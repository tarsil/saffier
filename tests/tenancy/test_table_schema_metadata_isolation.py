from saffier.contrib.multi_tenancy import TenantModel, TenantRegistry
from saffier.core.db import fields
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = TenantRegistry(database=database)


class User(TenantModel):
    id = fields.IntegerField(primary_key=True)
    name = fields.CharField(max_length=255)

    class Meta:
        registry = models
        is_tenant = True


class Product(TenantModel):
    id = fields.IntegerField(primary_key=True)
    name = fields.CharField(max_length=255)
    user = fields.ForeignKey(User, null=True)

    class Meta:
        registry = models
        is_tenant = True


def test_table_schema_does_not_pollute_registry_metadata() -> None:
    initial_keys = set(models.metadata.tables.keys())

    tenant_user_table = User.table_schema("tenant_1")
    tenant_product_table = Product.table_schema("tenant_1")

    assert tenant_user_table.schema == "tenant_1"
    assert tenant_product_table.schema == "tenant_1"
    assert set(models.metadata.tables.keys()) == initial_keys
    assert all(not key.startswith("tenant_1.") for key in models.metadata.tables)
