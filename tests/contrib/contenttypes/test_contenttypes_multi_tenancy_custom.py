import pytest

from saffier.contrib.contenttypes.models import ContentType as BaseContentType
from saffier.contrib.multi_tenancy import TenantModel, TenantRegistry
from saffier.contrib.multi_tenancy.models import TenantMixin
from saffier.core.db import fields
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL)


class ExplicitContentType(BaseContentType):
    class Meta:
        abstract = True


models = TenantRegistry(database=database, with_content_type=ExplicitContentType)


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


async def test_custom_content_type_is_concrete_and_tenant_aware():
    tenant = await Tenant.query.create(
        schema_name="tenant_custom_contenttype",
        domain_url="https://tenant-custom-contenttype.example.com",
        tenant_name="tenant-custom-contenttype",
    )

    user = await User.query.using(schema=tenant.schema_name).create(name="Tenant User")
    content_type = await models.content_type.query.get(id=user.content_type.id)

    assert models.content_type is models.get_model("ContentType", include_content_type_attr=False)
    assert content_type.schema_name == tenant.schema_name
    assert await content_type.get_instance() == user
