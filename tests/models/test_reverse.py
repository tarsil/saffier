import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class IntCounter(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=False)
    criteria2 = saffier.IntegerField(autoincrement=False, null=True)

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


async def test_reverse_default():
    await IntCounter.query.bulk_create([{"id": i} for i in range(100)])
    assert (await IntCounter.query.all())[0].id == 0
    assert (await IntCounter.query.first()).id == 0
    assert (await IntCounter.query.reverse().first()).id == 99
    assert (await IntCounter.query.reverse().last()).id == 0
    assert (await IntCounter.query.reverse().all().last()).id == 0
    assert (await IntCounter.query.reverse())[0].id == 99
    assert (await IntCounter.query.reverse().reverse())[0].id == 0


async def test_reverse_order_by():
    await IntCounter.query.bulk_create([{"id": i} for i in range(100)])
    assert (await IntCounter.query.order_by("id"))[0].id == 0
    assert (await IntCounter.query.order_by("id").first()).id == 0
    assert (await IntCounter.query.order_by("id").reverse().first()).id == 99
    assert (await IntCounter.query.order_by("id").reverse().last()).id == 0
    assert (await IntCounter.query.order_by("id").reverse().all().last()).id == 0
    assert (await IntCounter.query.order_by("id").reverse())[0].id == 99
    assert (await IntCounter.query.order_by("id").reverse().reverse())[0].id == 0

    await IntCounter.query.bulk_create([{"id": i, "criteria2": 1} for i in range(100, 200)])
    assert (await IntCounter.query.order_by("criteria2", "id"))[0].id == 100
    assert (await IntCounter.query.order_by("-criteria2", "id"))[0].id == 0
    assert (await IntCounter.query.order_by("criteria2", "id").reverse())[0].id == 99
    assert (await IntCounter.query.order_by("-criteria2", "id").reverse())[0].id == 199
