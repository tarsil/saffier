import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=saffier.Database(database, force_rollback=True))


class MyModel(saffier.Model):
    class Meta:
        registry = models


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


async def test_rollback1():
    assert await MyModel.query.all() == []
    assert bool(database.force_rollback())
    model = await MyModel.query.create()
    assert await MyModel.query.all() == [model]


async def test_rollback2():
    assert await MyModel.query.all() == []
    assert bool(database.force_rollback())
    model = await MyModel.query.create()
    assert await MyModel.query.all() == [model]
