import pytest

import saffier
from saffier.core.db.querysets.clauses import and_
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class User(saffier.Model):
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=200, null=True)
    email = saffier.EmailField(null=True, max_length=255)

    class Meta:
        registry = models


class Product(saffier.Model):
    user = saffier.ForeignKey(User, related_name="products")

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


async def test_filter_with_and():
    user = await User.query.create(name="Adam", language="EN")

    results = await User.query.filter(and_(User.columns.name == "Adam"))

    assert len(results) == 1
    assert results[0].pk == user.pk


async def test_filter_with_and_two():
    await User.query.create(name="Adam")
    await User.query.create(name="Saffier")

    results = await User.query.filter(
        and_(User.columns.name == "Adam", User.columns.name == "Saffier")
    )

    assert len(results) == 0


async def test_filter_with_and_three():
    await User.query.create(name="Adam")
    user = await User.query.create(name="Saffier", email="saffier@saffier.dev")

    results = await User.query.filter(
        and_(User.columns.name == user.name, User.columns.email == user.email)
    )

    assert len(results) == 1


async def test_filter_with_and_four():
    await User.query.create(name="Adam")
    user = await User.query.create(name="Saffier", email="saffier@saffier.dev")

    results = await User.query.filter(and_(User.columns.name == user.name)).filter(
        and_(User.columns.email == user.email)
    )
    assert len(results) == 1


async def test_filter_with_contains():
    await User.query.create(name="Adam", email="adam@saffier.dev")
    await User.query.create(name="Saffier", email="saffier@saffier.dev")

    results = await User.query.filter(and_(User.columns.email.contains("saffier")))
    assert len(results) == 2


async def test_filter_and_clause_style():
    user = await User.query.create(name="Adam", email="adam@saffier.dev")
    await User.query.create(name="Saffier", email="saffier@saffier.dev")

    results = await User.query.and_(name="Adam", email__icontains="saffier")

    assert len(results) == 1
    assert results[0].pk == user.pk

    results = await User.query.and_(email__icontains="saffier")

    assert len(results) == 2


async def test_filter_and_clause_style_nested():
    user = await User.query.create(name="Adam", email="adam@saffier.dev")
    await User.query.create(name="Saffier", email="saffier@saffier.dev")

    results = await User.query.and_(name="Adam").and_(email__icontains="saffier")

    assert len(results) == 1
    assert results[0].pk == user.pk


async def test_filter_and_clause_related():
    user = await User.query.create(name="Adam", email="adam@saffier.dev")
    await User.query.create(name="Saffier", email="saffier@saffier.dev")
    product = await Product.query.create(user=user)

    results = await Product.query.and_(user__id=user.pk)

    assert len(results) == 1
    assert results[0].pk == product.pk

    results = await User.query.and_(products__id=product.pk)

    assert len(results) == 1
    assert results[0].pk == user.pk
