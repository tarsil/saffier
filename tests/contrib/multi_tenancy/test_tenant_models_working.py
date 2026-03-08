from datetime import datetime

import pytest

from saffier.contrib.multi_tenancy import TenantModel, TenantRegistry
from saffier.contrib.multi_tenancy.models import TenantMixin
from saffier.core.db import fields
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = TenantRegistry(database=database)

pytestmark = pytest.mark.anyio


def time():
    return datetime.now().time()


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    try:
        await models.create_all()
        yield
        await models.drop_all()
    except Exception as e:
        pytest.skip(f"Error: {str(e)}")


@pytest.fixture(autouse=True)
async def rollback_connections():
    with database.force_rollback():
        async with database:
            yield


async def drop_schemas(name):
    await models.schema.drop_schema(name, if_exists=True)


class Tenant(TenantMixin):
    class Meta:
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
    user = fields.ForeignKey(User, null=True)

    class Meta:
        registry = models
        is_tenant = True


async def test_tenant_model_metaclass_tenant_models():
    assert Product.__name__ in Product.meta.registry.tenant_models


async def test_schema():
    tenant = await Tenant.query.create(
        schema_name="tenant_alpha",
        domain_url="https://tenant-alpha.saffier.test",
        tenant_name="tenant_alpha",
    )

    for i in range(5):
        await Product.query.using(tenant.schema_name).create(name=f"product-{i}")

    total = await Product.query.using(tenant.schema_name).all()

    assert len(total) == 5

    total = await Product.query.all()

    assert len(total) == 0

    for i in range(15):
        await Product.query.create(name=f"product-{i}")

    total = await Product.query.all()

    assert len(total) == 15

    total = await Product.query.using(tenant.schema_name).all()

    assert len(total) == 5


async def test_can_have_multiple_tenants_with_different_records():
    tenant_alpha = await Tenant.query.create(
        schema_name="tenant_alpha",
        domain_url="https://tenant-alpha.saffier.test",
        tenant_name="tenant_alpha",
    )
    tenant_beta = await Tenant.query.create(
        schema_name="tenant_beta",
        domain_url="https://tenant-beta.saffier.test",
        tenant_name="tenant_beta",
    )

    # Create a user for tenant alpha
    user_alpha = await User.query.using(tenant_alpha.schema_name).create(name="Saffier Alpha")

    # Create products for user_alpha
    for i in range(5):
        await Product.query.using(tenant_alpha.schema_name).create(
            name=f"product-{i}", user=user_alpha
        )

    # Create a user for tenant beta
    user_beta = await User.query.using(tenant_beta.schema_name).create(name="Saffier Beta")

    # Create products for user_beta
    for i in range(25):
        await Product.query.using(tenant_beta.schema_name).create(
            name=f"product-{i}", user=user_beta
        )

    # Create top level users
    for name in range(10):
        await User.query.using(tenant_beta.schema_name).create(name=f"user-{name}")
        await User.query.using(tenant_alpha.schema_name).create(name=f"user-{name}")
        await User.query.create(name=f"user-{name}")

    # Check the totals
    top_level_users = await User.query.all()
    assert len(top_level_users) == 10

    users_alpha = await User.query.using(tenant_alpha.schema_name).all()
    assert len(users_alpha) == 11

    users_beta = await User.query.using(tenant_beta.schema_name).all()
    assert len(users_beta) == 11


async def test_model_crud():
    tenant_alpha = await Tenant.query.create(
        schema_name="tenant_alpha",
        domain_url="https://tenant-alpha.saffier.test",
        tenant_name="tenant_alpha",
    )

    users = await User.query.using(tenant_alpha.schema_name).all()
    assert users == []

    user = await User.query.using(tenant_alpha.schema_name).create(name="Test")
    users = await User.query.using(tenant_alpha.schema_name).all()
    assert user.name == "Test"
    assert user.pk is not None
    assert users == [user]

    lookup = await User.query.using(tenant_alpha.schema_name).get()
    assert lookup == user

    await user.update(name="Jane")
    users = await User.query.using(tenant_alpha.schema_name).all()
    assert user.name == "Jane"
    assert user.pk is not None
    assert users == [user]

    # Check if public has the users
    users = await User.query.all()
    assert users == []

    await user.delete()
    users = await User.query.using(tenant_alpha.schema_name).all()
    assert users == []
