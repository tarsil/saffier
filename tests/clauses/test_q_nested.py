import pytest

import saffier
from saffier.core.db.querysets.clauses import Q
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=200, null=True)
    email = saffier.EmailField(null=True, max_length=255)
    products = saffier.ManyToManyField("Product")

    class Meta:
        registry = models


class Product(saffier.Model):
    name = saffier.CharField(max_length=100)
    role = saffier.ForeignKey("Role", null=True)

    class Meta:
        registry = models


class Role(saffier.Model):
    name = saffier.CharField(max_length=100)

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


async def test_q_nested_many_to_many_tree():
    user = await User.query.create(name="Adam", email="adam@saffier.dev")
    role = await Role.query.create(name="shelf")
    product = await Product.query.create(name="soap")
    product2 = await Product.query.create(name="potatos", role=role)

    await user.products.add_many(product, product2)

    expression = (
        Q(name="Adam")
        | Q(products__name__icontains="soap")
        | Q(products__role__name__icontains="shelf")
    )

    results = await User.query.filter(expression).distinct("id")

    assert len(results) == 1
    assert results[0].pk == user.pk
