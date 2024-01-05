import pytest
from pydantic import __version__

from saffier import fields
from saffier.contrib.multi_tenancy import TenantModel, TenantRegistry
from saffier.contrib.multi_tenancy.models import TenantMixin
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = TenantRegistry(database=database)


pytestmark = pytest.mark.anyio
pydantic_version = __version__[:3]


class Tenant(TenantMixin):
    class Meta:
        registry = models


class User(TenantModel):
    name = fields.CharField(max_length=255)

    class Meta:
        registry = models
        is_tenant = True


class Product(TenantModel):
    name = fields.CharField(max_length=255)
    user = fields.ForeignKey(User, null=True, related_name="products")

    class Meta:
        registry = models
        is_tenant = True


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    try:
        await models.create_all()
        yield
        await models.drop_all()
    except Exception:
        pytest.skip("No database available")


@pytest.fixture(autouse=True)
async def rollback_connections():
    with database.force_rollback():
        async with database:
            yield


async def test_queries():
    tenant = await Tenant.query.create(schema_name="saffier", tenant_name="saffier")

    # Create a product with a user
    user = await User.query.using(tenant.schema_name).create(name="user")
    product = await Product.query.using(tenant.schema_name).create(name="product-1", user=user)

    # Query tenants
    users = await User.query.using(tenant.schema_name).all()
    assert len(users) == 1

    products = await Product.query.using(tenant.schema_name).all()
    assert len(products) == 1

    # Query related
    prod = await Product.query.using(tenant.schema_name).filter(user__name__icontains="u").get()

    assert prod.id == product.id
    assert prod.table.schema == tenant.schema_name
