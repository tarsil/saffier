import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=200, null=True)

    class Meta:
        registry = models


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


async def test_get_or_none():
    user = saffier.run_sync(User.query.create(name="Charles"))
    assert user == saffier.run_sync(User.query.filter(name="Charles").get())

    user = saffier.run_sync(User.query.get_or_none(name="Luigi"))
    assert user is None

    user = saffier.run_sync(User.query.get_or_none(name="Charles"))
    assert user.pk == 1


async def test_get_or_none_without_get():
    user = saffier.run_sync(User.query.create(name="Charles"))
    users = saffier.run_sync(User.query.filter(name="Charles"))
    assert user == users[0]

    user = saffier.run_sync(User.query.get_or_none(name="Luigi"))
    assert user is None

    user = saffier.run_sync(User.query.get_or_none(name="Charles"))
    assert user.pk == 1
