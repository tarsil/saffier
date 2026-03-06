import pytest

import saffier
from saffier.contrib.permissions import BasePermission
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL, use_existing=False)
models = saffier.Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=100, unique=True)

    class Meta:
        registry = models


class Permission(BasePermission):
    users = saffier.ManyToMany("User")

    class Meta:
        registry = models
        unique_together = [("name",)]

    @classmethod
    def get_description(cls, field, instance, owner=None) -> str:
        return instance.name.upper()

    @classmethod
    def set_description(cls, field, instance, value, owner=None) -> None:
        instance.__dict__["description_write"] = value


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


async def test_permission_computed_description():
    permission = await Permission.query.create(name="View")
    assert permission.description == "VIEW"
    permission.description = "tool"
    assert permission.description_write == "tool"


async def test_querying_permissions_for_user():
    user = await User.query.create(name="edgy")
    permission = await Permission.query.create(users=[user], name="view")

    assert await Permission.query.users("view").get() == user
    assert await Permission.query.users("edit").count() == 0
    assert await Permission.query.permissions_of(user).get() == permission
