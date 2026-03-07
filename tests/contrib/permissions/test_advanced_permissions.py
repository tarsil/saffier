import pytest

import saffier
from saffier.contrib.permissions import BasePermission
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL, use_existing=False)
models = saffier.Registry(database=saffier.Database(database, force_rollback=True), with_content_type=True)


class User(saffier.StrictModel):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Group(saffier.StrictModel):
    name = saffier.CharField(max_length=100)
    users = saffier.ManyToMany("User", through_tablename=saffier.NEW_M2M_NAMING)

    class Meta:
        registry = models


class Permission(BasePermission):
    users = saffier.ManyToMany("User", through_tablename=saffier.NEW_M2M_NAMING)
    groups = saffier.ManyToMany("Group", through_tablename=saffier.NEW_M2M_NAMING)
    name_model = saffier.CharField(max_length=100, null=True)
    obj = saffier.ForeignKey("ContentType", null=True)

    class Meta:
        registry = models
        unique_together = [("name", "name_model", "obj")]


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    async with database:
        await models.create_all()
        yield
        if not database.drop:
            await models.drop_all()


@pytest.fixture(autouse=True, scope="function")
async def rollback_transactions():
    async with models:
        yield


async def test_querying():
    user = await User.query.create(name="edgy")
    permission = await Permission.query.create(users=[user], name="view", obj=user.content_type)

    assert await Permission.query.users("view").get() == user
    assert await Permission.query.users("edit").count() == 0
    assert await Permission.query.permissions_of(user).get() == permission


async def test_querying_mixed():
    user = await User.query.create(name="edgy")
    group = await Group.query.create(name="admin", users=[user])
    await Permission.query.create(users=[user], name="view")
    permission2 = await Permission.query.create(groups=[group], name="admin")

    assert await Permission.query.filter(name="admin").get()

    permissions = await Permission.query.permissions_of(user)
    assert len(permissions) == 2

    permissions = await Permission.query.permissions_of(group)
    assert permissions == [permission2]

    assert await Permission.query.users("view").get() == user
    assert await Permission.query.users("admin").get() == user
    assert await Permission.query.users("edit").count() == 0
    assert await Permission.query.permissions_of(user).count() == 2
