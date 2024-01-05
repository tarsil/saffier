import pytest

import saffier
from saffier.exceptions import MultipleObjectsReturned, ObjectNotFound
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


class Product(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)
    rating = saffier.IntegerField(minimum=1, maximum=5)
    in_stock = saffier.BooleanField(default=False)

    class Meta:
        registry = models
        name = "products"


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


async def test_model_crud():
    users = saffier.run_sync(User.query.all())
    assert users == []

    user = saffier.run_sync(User.query.create(name="Test"))
    users = saffier.run_sync(User.query.all())
    assert user.name == "Test"
    assert user.pk is not None
    assert users == [user]

    lookup = saffier.run_sync(User.query.get())
    assert lookup == user

    saffier.run_sync(user.update(name="Jane"))
    users = saffier.run_sync(User.query.all())
    assert user.name == "Jane"
    assert user.pk is not None
    assert users == [user]

    saffier.run_sync(user.delete())
    users = saffier.run_sync(User.query.all())
    assert users == []


async def test_model_get():
    with pytest.raises(ObjectNotFound):
        saffier.run_sync(User.query.get())

    user = saffier.run_sync(User.query.create(name="Test"))
    lookup = saffier.run_sync(User.query.get())
    assert lookup == user

    user = saffier.run_sync(User.query.create(name="Jane"))
    with pytest.raises(MultipleObjectsReturned):
        saffier.run_sync(User.query.get())

    same_user = saffier.run_sync(User.query.get(pk=user.id))
    assert same_user.id == user.id
    assert same_user.pk == user.pk
