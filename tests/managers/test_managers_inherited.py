import pytest

import saffier
from saffier import Manager
from saffier.db.querysets.queryset import QuerySet
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class ObjectsManager(Manager):
    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset().filter(is_active=True)
        return queryset


class LanguageManager(Manager):
    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset().filter(language="EN")
        return queryset


class RatingManager(Manager):
    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset().filter(rating__gte=3)
        return queryset


class BaseModel(saffier.Model):
    query = ObjectsManager()
    languages = LanguageManager()
    ratings = RatingManager()

    class Meta:
        registry = models


class User(BaseModel):
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=200, null=True)

    class Meta:
        registry = models


class Product(BaseModel):
    name = saffier.CharField(max_length=100)
    rating = saffier.IntegerField(minimum=1, maximum=5)
    in_stock = saffier.BooleanField(default=False)
    is_active = saffier.BooleanField(default=False)


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


async def test_inherited_base_model_managers():
    await User.query.create(name="test", language="EN")
    await User.query.create(name="test2", language="EN")
    await User.query.create(name="test3", language="PT")
    await User.query.create(name="test4", language="PT")

    users = await User.query.all()
    assert len(users) == 4

    users = await User.languages.all()
    assert len(users) == 2


@pytest.mark.parametrize("manager,total", [("query", 6), ("ratings", 3)])
async def test_inherited_base_model_managers_product(manager, total):
    await Product.query.create(name="test", rating=5)
    await Product.query.create(name="test2", rating=4)
    await Product.query.create(name="test3", rating=3)
    await Product.query.create(name="test4", rating=2)
    await Product.query.create(name="test5", rating=2)
    await Product.query.create(name="test6", rating=1)

    products = await getattr(Product, manager).all()
    assert len(products) == total


async def test_raises_key_error_on_non_existing_field_for_product():
    await Product.query.create(name="test", rating=5)

    with pytest.raises(KeyError):
        await Product.languages.all()


async def test_raises_key_error_on_non_existing_field_for_user():
    await User.query.create(name="test", language="EN")

    with pytest.raises(KeyError):
        await User.ratings.all()
