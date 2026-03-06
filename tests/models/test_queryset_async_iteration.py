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


async def test_async_iteration_respects_batch_size():
    await User.query.bulk_create(
        [
            {"name": "Alice"},
            {"name": "Bob"},
            {"name": "Carol"},
        ]
    )

    names = []
    async for user in User.query.order_by("id").batch_size(1):
        names.append(user.name)

    assert names == ["Alice", "Bob", "Carol"]


async def test_async_iteration_respects_all_kwargs():
    await User.query.bulk_create(
        [
            {"name": "Alice"},
            {"name": "Bob"},
        ]
    )

    names = []
    async for user in User.query.all(name="Alice"):
        names.append(user.name)

    assert names == ["Alice"]
