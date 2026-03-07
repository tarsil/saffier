import pytest

from saffier.contrib.multi_tenancy import TenantModel, TenantRegistry
from saffier.contrib.multi_tenancy.models import TenantMixin
from saffier.core.db import fields
from saffier.exceptions import ObjectNotFound
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

database = DatabaseTestClient(DATABASE_URL)
models = TenantRegistry(database=database)

pytestmark = pytest.mark.anyio


class Tenant(TenantMixin):
    class Meta:
        registry = models


class User(TenantModel):
    id = fields.IntegerField(primary_key=True, autoincrement=True)
    name = fields.CharField(max_length=255)
    email = fields.EmailField(max_length=255)

    class Meta:
        registry = models
        is_tenant = True


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_transactions():
    with database.force_rollback():
        async with database:
            yield


async def test_schema_using_update_preserves_other_columns():
    tenant = await Tenant.query.create(
        schema_name="using_ops",
        domain_url="https://using-ops.example.com",
        tenant_name="using-ops",
    )

    user = await User.query.using(schema=tenant.schema_name).create(
        name="Edgy",
        email="edgy@edgy.dev",
    )
    users = await User.query.using(schema=tenant.schema_name).all()

    assert user.email == "edgy@edgy.dev"
    assert len(users) == 1

    await (
        User.query.using(schema=tenant.schema_name)
        .filter(email="edgy@edgy.dev")
        .update(email="bar@foo.com")
    )

    users = await User.query.using(schema=tenant.schema_name).all()
    assert len(users) == 1
    assert users[0].email == "bar@foo.com"
    assert users[0].name == "Edgy"

    loaded = await User.query.using(schema=tenant.schema_name).get(email="bar@foo.com")
    assert loaded.email == "bar@foo.com"
    assert loaded.name == "Edgy"

    with pytest.raises(ObjectNotFound):
        await User.query.using(schema=tenant.schema_name).get(email="edgy@edgy.dev")
