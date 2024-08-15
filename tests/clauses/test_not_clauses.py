import pytest

import saffier
from saffier.core.db.querysets.clauses import not_
from tests.settings import DATABASE_URL

database = saffier.Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=200, null=True)
    email = saffier.EmailField(null=True, max_length=255)

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


async def test_filter_with_not():
    await User.query.create(name="Adam", language="EN")

    results = await User.query.filter(not_(User.columns.name == "Adam"))

    assert len(results) == 0


async def test_filter_with_not_two():
    await User.query.create(name="Adam")
    await User.query.create(name="Saffier")
    user = await User.query.create(name="Esmerald")

    results = await User.query.filter(not_(User.columns.name == "Saffier")).filter(
        not_(User.columns.name == "Adam")
    )

    assert len(results) == 1
    assert results[0].pk == user.pk


async def test_filter_with_not_style():
    await User.query.create(name="Adam")
    await User.query.create(name="Saffier")
    user = await User.query.create(name="Esmerald")

    results = await User.query.not_(name="Saffier").not_(name="Adam")

    assert len(results) == 1
    assert results[0].pk == user.pk
