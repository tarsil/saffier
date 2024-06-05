from typing import Optional

import pytest
from pydantic import __version__

import saffier
from saffier.contrib.multi_tenancy import TenantRegistry
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = TenantRegistry(database=database)


pytestmark = pytest.mark.anyio
pydantic_version = __version__[:3]


class EdgyTenantBaseModel(saffier.Model):
    id: int = saffier.IntegerField(primary_key=True)

    class Meta:
        registry = models
        abstract = True


class Profle(saffier.Model):
    id: int = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)
    profile: Profle = saffier.ForeignKey(Profle)

    class Meta:
        registry = models


class Designation(EdgyTenantBaseModel):
    name: str = saffier.CharField(max_length=100)
    user: User = saffier.ForeignKey(User, null=True)

    class Meta:
        tablename = "ut_designation"


class AppModule(EdgyTenantBaseModel):
    name: str = saffier.CharField(max_length=100)

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


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connections():
    with database.force_rollback():
        async with database:
            yield


async def test_inner_select():
    designation = await Designation.query.create(name="admin")
    module = await AppModule.query.create(name="payroll")

    await Permission.query.create(designation=designation, module=module)

    query = await Permission.query.all()

    assert len(query) == 1

    query = await Permission.query.first()

    name = query.designation.name

    assert name == designation.name


async def test_inner_select_nested():
    profile = await Profle.query.create(name="super_admin")
    user = await User.query.create(name="user", profile=profile)
    designation = await Designation.query.create(name="admin", user=user)
    module = await AppModule.query.create(name="payroll")

    await Permission.query.create(designation=designation, module=module)

    query = await Permission.query.all()

    assert len(query) == 1

    query = await Permission.query.first()

    name = query.designation.name

    assert name == designation.name
    assert query.designation.user.name == user.name
    assert query.designation.user.profile.name == profile.name


async def test_raise_attribute_error_select():
    designation = await Designation.query.create(name="admin")
    module = await AppModule.query.create(name="payroll")

    await Permission.query.create(designation=designation, module=module)

    query = await Permission.query.all()

    assert len(query) == 1

    query = await Permission.query.first()

    with pytest.raises(AttributeError):
        query.designation.test  # noqa
