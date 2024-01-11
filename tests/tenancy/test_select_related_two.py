from typing import Optional

import pytest
from pydantic import __version__

import saffier
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


class EdgyTenantBaseModel(TenantModel):
    id = saffier.IntegerField(primary_key=True)

    class Meta:
        is_tenant = True
        registry = models
        abstract = True


class Designation(EdgyTenantBaseModel):
    name = saffier.CharField(max_length=100)

    class Meta:
        tablename = "ut_designation"


class AppModule(EdgyTenantBaseModel):
    name = saffier.CharField(max_length=100)

    class Meta:
        tablename = "ut_module"


class Permission(EdgyTenantBaseModel):
    module: Optional[AppModule] = saffier.ForeignKey(AppModule)
    designation: Optional[Designation] = saffier.ForeignKey("Designation")
    can_read: bool = saffier.BooleanField(default=False)
    can_write: bool = saffier.BooleanField(default=False)
    can_update: bool = saffier.BooleanField(default=False)
    can_delete: bool = saffier.BooleanField(default=False)
    can_approve: bool = saffier.BooleanField(default=False)

    class Meta:
        tablename = "ut_permission"


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
    designation = await Designation.query.using(tenant.schema_name).create(name="admin")
    module = await AppModule.query.using(tenant.schema_name).create(name="payroll")

    permission = await Permission.query.using(tenant.schema_name).create(
        designation=designation, module=module
    )

    query = await Permission.query.all()

    assert len(query) == 0

    query = await Permission.query.using(tenant.schema_name).select_related("designation").all()

    assert len(query) == 1
    assert query[0].pk == permission.pk
