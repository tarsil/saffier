import pytest
from tests.settings import DATABASE_URL

import saffier
from saffier import Database

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connections():
    with database.force_rollback():
        async with database:
            yield


async def test_meta_tablename():
    await User.query.create(name="Saffier")
    users = await User.query.all()

    assert len(users) == 1

    user = await User.query.get(name="Saffier")

    assert user._meta.tablename == "users"


async def test_meta_registry():
    await User.query.create(name="Saffier")
    users = await User.query.all()

    assert len(users) == 1

    user = await User.query.get(name="Saffier")

    assert user._meta.registry == models
