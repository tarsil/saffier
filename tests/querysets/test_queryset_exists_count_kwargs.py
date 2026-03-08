import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=255)
    email = saffier.CharField(max_length=255, null=True)

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connection():
    with database.force_rollback():
        async with database:
            yield


async def test_exists_and_count_accept_lookup_kwargs():
    await User.query.create(name="Alice", email="alice@example.com")
    await User.query.create(name="Bob", email=None)

    assert await User.query.exists(name="Alice")
    assert not await User.query.exists(name="Charlie")
    assert await User.query.exists(email__isnull=True)

    assert await User.query.count(name="Alice") == 1
    assert await User.query.count(email__isnull=True) == 1
    assert await User.query.count(name__icontains="o") == 1
