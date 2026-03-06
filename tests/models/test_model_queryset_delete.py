import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


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


async def test_queryset_delete():
    shirt = await Product.query.create(name="Shirt", rating=5)
    await Product.query.create(name="Belt", rating=5)
    await Product.query.create(name="Tie", rating=5)

    deleted = await Product.query.filter(pk=shirt.id).delete()
    assert deleted == 1
    assert await Product.query.count() == 2

    deleted = await Product.query.delete()
    assert deleted == 2
    assert await Product.query.count() == 0


async def test_raw_delete_respects_or_clauses():
    await Product.query.create(name="Shirt", rating=5)
    await Product.query.create(name="Belt", rating=5)
    await Product.query.create(name="Tie", rating=5)

    deleted = await Product.query.local_or(name="Shirt").local_or(name="Belt").raw_delete()

    assert deleted == 2
    assert await Product.query.count() == 1


async def test_queryset_delete_use_models_returns_row_count():
    await Product.query.create(name="Shirt", rating=5)
    await Product.query.create(name="Belt", rating=5)
    await Product.query.create(name="Tie", rating=5)

    deleted = await Product.query.delete(use_models=True)

    assert deleted == 3
    assert await Product.query.count() == 0
