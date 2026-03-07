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


async def test_model_last():
    Test = await User.query.create(name="Test")
    jane = await User.query.create(name="Jane")

    assert await User.query.last() == jane
    assert await User.query.last(name="Jane") == jane
    assert await User.query.filter(name="Test").last() == Test
    assert await User.query.filter(name="Lucy").last() is None


async def test_model_last_respects_existing_ordering():
    await User.query.create(name="Zulu")
    alpha = await User.query.create(name="Alpha")

    last = await User.query.order_by("name").last()

    assert last != alpha
    assert last is not None
    assert last.name == "Zulu"
