import pytest
from pydantic import __version__

import saffier
from saffier.contrib.multi_tenancy import TenantModel, TenantRegistry
from saffier.contrib.multi_tenancy.models import TenantMixin
from saffier.core.db.querysets.mixins import activate_schema, deativate_schema
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = TenantRegistry(database=database)


pytestmark = pytest.mark.anyio
pydantic_version = __version__[:3]


class Tenant(TenantMixin):
    class Meta:
        registry = models


class SaffierTenantBaseModel(TenantModel):
    id = saffier.IntegerField(primary_key=True)

    class Meta:
        is_tenant = True
        registry = models
        abstract = True


class Designation(SaffierTenantBaseModel):
    name = saffier.CharField(max_length=100)

    class Meta:
        tablename = "ut_designation"


class AppModule(SaffierTenantBaseModel):
    name = saffier.CharField(max_length=100)

    class Meta:
        tablename = "ut_module"


class Permission(SaffierTenantBaseModel):
    module = saffier.ForeignKey(AppModule)
    designation = saffier.ForeignKey("Designation")
    can_read = saffier.BooleanField(default=False)
    can_write = saffier.BooleanField(default=False)
    can_update = saffier.BooleanField(default=False)
    can_delete = saffier.BooleanField(default=False)
    can_approve = saffier.BooleanField(default=False)

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


async def test_activate_related_tenant():
    tenant = await Tenant.query.create(schema_name="saffier", tenant_name="saffier")

    # Activate the schema and query always the tenant set
    activate_schema(tenant.schema_name)
    designation = await Designation.query.create(name="admin")
    module = await AppModule.query.create(name="payroll")

    permission = await Permission.query.create(designation=designation, module=module)

    query = await Permission.query.all()

    assert len(query) == 1
    assert query[0].pk == permission.pk

    # Deactivate the schema and set to None (default)
    deativate_schema()

    query = await Permission.query.all()

    assert len(query) == 0

    # Even if the activate_schema is enabled
    # The use of `using` takes precedence
    query = await Permission.query.using(tenant.schema_name).select_related("designation").all()

    assert len(query) == 1
    assert query[0].pk == permission.pk
