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


async def test_model_sqlalchemy_filter_operators():
    user = await User.query.create(name="George")

    assert user == await User.query.filter(User.columns.name == "George").get()
    assert user == await User.query.filter(User.columns.name.is_not(None)).get()
    assert (
        user
        == await User.query.filter(User.columns.name.startswith("G"))
        .filter(User.columns.name.endswith("e"))
        .get()
    )

    assert user == await User.query.exclude(User.columns.name != "Jack").get()

    shirt = await Product.query.create(name="100%-Cotton", rating=3)
    assert shirt == await Product.query.filter(Product.columns.name.contains("Cotton")).get()


async def test_model_sqlalchemy_filter_operators_no_get():
    user = await User.query.create(name="George")
    users = await User.query.filter(User.columns.name == "George")
    assert user == users[0]

    users = await User.query.filter(User.columns.name.is_not(None))
    assert user == users[0]

    users = await User.query.filter(User.columns.name.startswith("G")).filter(
        User.columns.name.endswith("e")
    )
    assert user == users[0]

    assert user == await User.query.exclude(User.columns.name != "Jack").get()

    shirt = await Product.query.create(name="100%-Cotton", rating=3)
    shirts = await Product.query.filter(Product.columns.name.contains("Cotton"))
    assert shirt == shirts[0]
