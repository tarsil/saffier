import pytest

from saffier.contrib.multi_tenancy import TenantModel, TenantRegistry
from saffier.contrib.multi_tenancy.models import TenantMixin
from saffier.core.db import fields
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL)
models = TenantRegistry(database=database, with_content_type=True)


class Tenant(TenantMixin):
    class Meta:
        registry = models


class User(TenantModel):
    id = fields.IntegerField(primary_key=True, autoincrement=True)
    name = fields.CharField(max_length=255)

    class Meta:
        registry = models
        is_tenant = True
        register_default = False


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    try:
        await models.create_all()
        yield
        await models.drop_all()
    except Exception as exc:
        pytest.skip(f"Error: {exc}")


@pytest.fixture(autouse=True)
async def rollback_connections():
    with database.force_rollback():
        async with database:
            yield


async def test_tenant_content_type_tracks_schema_name_and_get_instance():
    tenant = await Tenant.query.create(
        schema_name="tenant_contenttype",
        domain_url="https://tenant-contenttype.example.com",
        tenant_name="tenant-contenttype",
    )

    user = await User.query.using(schema=tenant.schema_name).create(name="Tenant User")
    content_type = await models.content_type.query.get(id=user.content_type.id)

    assert content_type.schema_name == tenant.schema_name
    assert await content_type.get_instance() == user


async def test_deleting_tenant_content_type_cascades_tenant_rows():
    tenant = await Tenant.query.create(
        schema_name="tenant_contenttype_delete",
        domain_url="https://tenant-contenttype-delete.example.com",
        tenant_name="tenant-contenttype-delete",
    )

    user = await User.query.using(schema=tenant.schema_name).create(name="Tenant Delete User")
    await models.content_type.query.filter(id=user.content_type.id).delete()

    assert await User.query.using(schema=tenant.schema_name).count() == 0
