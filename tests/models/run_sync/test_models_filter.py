import pytest

import saffier
from saffier.exceptions import ObjectNotFound
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class User(saffier.Model):
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=200, null=True)

    class Meta:
        registry = models


class Product(saffier.Model):
    name = saffier.CharField(max_length=100)
    rating = saffier.IntegerField(minimum=1, maximum=5)
    in_stock = saffier.BooleanField(default=False)
    user = saffier.ForeignKey(User, null=True, on_delete=saffier.CASCADE)

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


async def test_filter_with_foreign_key():
    user = saffier.run_sync(User.query.create(name="Adam"))

    for _ in range(5):
        saffier.run_sync(Product.query.create(name="sku", user=user, rating=4))

    products = saffier.run_sync(Product.query.filter(user=user))

    assert len(products) == 5
    products = saffier.run_sync(Product.query.filter(user__id=user.pk))

    assert len(products) == 5


async def test_model_filter():
    saffier.run_sync(User.query.create(name="Test"))
    saffier.run_sync(User.query.create(name="Jane"))
    saffier.run_sync(User.query.create(name="Lucy"))

    user = saffier.run_sync(User.query.get(name="Lucy"))
    assert user.name == "Lucy"

    with pytest.raises(ObjectNotFound):
        saffier.run_sync(User.query.get(name="Jim"))

    saffier.run_sync(Product.query.create(name="T-Shirt", rating=5, in_stock=True))
    saffier.run_sync(Product.query.create(name="Dress", rating=4))
    saffier.run_sync(Product.query.create(name="Coat", rating=3, in_stock=True))

    product = saffier.run_sync(Product.query.get(name__iexact="t-shirt", rating=5))
    assert product.pk is not None
    assert product.name == "T-Shirt"
    assert product.rating == 5

    products = saffier.run_sync(Product.query.all(rating__gte=2, in_stock=True))
    assert len(products) == 2

    products = saffier.run_sync(Product.query.all(name__icontains="T"))
    assert len(products) == 2

    # Test escaping % character from icontains, contains, and iexact
    saffier.run_sync(Product.query.create(name="100%-Cotton", rating=3))
    saffier.run_sync(Product.query.create(name="Cotton-100%-Egyptian", rating=3))
    saffier.run_sync(Product.query.create(name="Cotton-100%", rating=3))
    products = Product.query.filter(name__iexact="100%-cotton")
    assert saffier.run_sync(products.count()) == 1

    products = Product.query.filter(name__contains="%")
    assert saffier.run_sync(products.count()) == 3

    products = Product.query.filter(name__icontains="%")
    assert saffier.run_sync(products.count()) == 3

    products = Product.query.exclude(name__iexact="100%-cotton")
    assert saffier.run_sync(products.count()) == 5

    products = Product.query.exclude(name__contains="%")
    assert saffier.run_sync(products.count()) == 3

    products = Product.query.exclude(name__icontains="%")
    assert saffier.run_sync(products.count()) == 3


async def test_model_nested_filter():
    saffier.run_sync(User.query.create(name="Test", language="EN"))
    saffier.run_sync(User.query.create(name="Test", language="ES"))
    saffier.run_sync(User.query.create(name="Test", language="PT"))
    saffier.run_sync(User.query.create(name="Jane", language="ES"))
    saffier.run_sync(User.query.create(name="Lucy", language="PT"))

    users = saffier.run_sync(User.query.filter(name="Test").filter(language="EN"))

    assert len(users) == 1

    users = saffier.run_sync(
        User.query.filter(name="Test").filter(language="EN").filter(language="PT")
    )

    assert len(users) == 0
