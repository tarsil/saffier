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


class Base(TenantModel):
    class Meta:
        abstract = True
        registry = models


class User(TenantModel):
    id = fields.IntegerField(primary_key=True)
    name = fields.CharField(max_length=255)

    class Meta:
        registry = models
        is_tenant = True


class Product(TenantModel):
    id = fields.IntegerField(primary_key=True)
    name = fields.CharField(max_length=255)
    user: User = fields.ForeignKey(User, null=True, related_name="products")

    class Meta:
        registry = models
        is_tenant = True


@pytest.fixture(autouse=True, scope="function")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connections():
    with database.force_rollback():
        async with database:
            yield


async def test_select_related_tenant():
    tenant = await Tenant.query.create(schema_name="saffier", tenant_name="saffier")

    # Create a product with a user
    user = await User.query.using(tenant.schema_name).create(name="user")
    product = await Product.query.using(tenant.schema_name).create(name="product-1", user=user)

    prod = await Product.query.using(tenant.schema_name).select_related("user").get(pk=1)

    assert prod.pk == product.pk
    assert prod.user.name == "user"
