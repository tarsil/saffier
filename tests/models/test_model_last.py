import pytest
from tests.settings import DATABASE_URL

import saffier
from saffier import Database

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
