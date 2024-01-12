import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class Main(saffier.Model):
    name = saffier.CharField(max_length=255)

    class Meta:
        registry = models


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)
    age = saffier.IntegerField(secret=True)
    language = saffier.CharField(max_length=200, null=True, secret=True)
    main = saffier.ForeignKey(Main, related_name="users", secret=True, null=True)

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


async def test_exclude_secrets():
    await User.query.create(name="Edgy", age=2, language="EN")
    await User.query.create(name="Saffier", age=2, language="EN")

    results = await User.query.exclude_secrets(id=1)

    assert len(results) == 1

    user = results[0]

    assert user.model_dump() == {"id": 1, "name": "Edgy"}

    results = await User.query.exclude_secrets(id=2).get()

    assert results.model_dump() == {"id": 2, "name": "Saffier"}


async def test_exclude_secrets_fk():
    main = await Main.query.create(name="main")
    await User.query.create(name="Edgy", age=2, language="EN", main=main)

    results = await User.query.exclude_secrets(id=1)

    assert len(results) == 1

    user = results[0]

    assert user.model_dump() == {"id": 1, "name": "Edgy"}


async def test_exclude_secrets_filter():
    main = await Main.query.create(name="main")
    await User.query.create(name="Edgy", age=2, language="EN", main=main)

    results = await User.query.filter(id=1).exclude_secrets()

    assert len(results) == 1

    user = results[0]

    assert user.model_dump() == {"id": 1, "name": "Edgy"}


async def test_exclude_secrets_various():
    main = await Main.query.create(name="main")
    await User.query.create(name="Edgy", age=2, language="EN", main=main)

    results = await User.query.only("id").exclude_secrets()

    assert len(results) == 1

    user = results[0]

    assert user.model_dump() == {"id": 1}
