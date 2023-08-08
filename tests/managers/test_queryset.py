import pytest

import saffier
from saffier import Manager
from saffier.db.querysets.queryset import QuerySet
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class ActiveManager(Manager):
    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset().filter(is_active=True)
        return queryset


class User(saffier.Model):
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=200, null=True)

    class Meta:
        registry = models


class Product(saffier.Model):
    active = ActiveManager()

    name = saffier.CharField(max_length=100)
    rating = saffier.IntegerField(minimum=1, maximum=5)
    in_stock = saffier.BooleanField(default=False)
    is_active = saffier.BooleanField(default=False)

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


async def test_contains():
    users = await User.query.all()
    assert users == []

    user = await User.query.create(name="Test")

    exists = await User.query.contains(user)

    assert exists is True


async def test_contains_false():
    users = await User.query.all()
    assert users == []

    user = await User.query.create(name="Test")

    exists = await Product.query.contains(user)

    assert exists is False
