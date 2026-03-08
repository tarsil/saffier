import pytest

import saffier
from saffier.contrib.permissions import BasePermission
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL, use_existing=False)
models = saffier.Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Group(saffier.Model):
    name = saffier.CharField(max_length=100)
    users = saffier.ManyToMany("User")

    class Meta:
        registry = models


class Permission(BasePermission):
    users = saffier.ManyToMany("User")
    groups = saffier.ManyToMany("Group")

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    async with database:
        await models.create_all()
        yield
        if not database.drop:
            await models.drop_all()


async def test_querying_via_group():
    user = await User.query.create(name="edgy")
    group = await Group.query.create(name="admin", users=[user])
    permission = await Permission.query.create(groups=[group], name="admin")

    permissions = await Permission.query.permissions_of(group)
    assert permissions == [permission]


async def test_querying_mixed_group_and_user():
    user = await User.query.create(name="edgy2")
    group = await Group.query.create(name="admin2", users=[user])
    await Permission.query.create(users=[user], name="view")
    grouped = await Permission.query.create(groups=[group], name="admin")

    permissions = await Permission.query.permissions_of(user)
    assert len(permissions) == 2

    permissions = await Permission.query.permissions_of(group)
    assert permissions == [grouped]

    assert await Permission.query.users("view").get() == user
    assert await Permission.query.users("admin").filter(pk=user.pk).exists()
    assert await Permission.query.users("edit").count() == 0
