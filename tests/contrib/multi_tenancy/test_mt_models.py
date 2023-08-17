from datetime import datetime
from enum import Enum

import pytest

from saffier.contrib.multi_tenancy import TenantModel, TenantRegistry
from saffier.contrib.multi_tenancy.exceptions import ModelSchemaError
from saffier.contrib.multi_tenancy.models import TenantMixin
from saffier.core.db import fields
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = TenantRegistry(database=database)

pytestmark = pytest.mark.anyio


def time():
    return datetime.now().time()


class StatusEnum(Enum):
    DRAFT = "Draft"
    RELEASED = "Released"


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


class Tenant(TenantMixin):
    class Meta:
        registry = models


class Product(TenantModel):
    id = fields.IntegerField(primary_key=True)
    uuid = fields.UUIDField(null=True)

    class Meta:
        registry = models
        is_tenant = True


async def test_create_a_tenant_schema():
    tenant = await Tenant.query.create(
        schema_name="saffier", domain_url="https://saffier.tarsild.io", tenant_name="saffier"
    )

    assert tenant.schema_name == "saffier"
    assert tenant.tenant_name == "saffier"


async def test_raises_ModelSchemaError_on_public_schema():
    with pytest.raises(ModelSchemaError) as raised:
        await Tenant.query.create(
            schema_name="public", domain_url="https://saffier.tarsild.io", tenant_name="saffier"
        )

    assert (
        raised.value.args[0]
        == "Can't update tenant outside it's own schema or the public schema. Current schema is 'public'"
    )
