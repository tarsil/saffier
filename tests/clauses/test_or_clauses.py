import pytest

import saffier
from saffier.core.db.querysets.clauses import or_
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
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


async def test_filter_with_or():
    user = await User.query.create(name="Adam")

    results = await User.query.filter(
        or_(User.columns.name == "Adam", User.columns.name == "Saffier")
    )

    assert len(results) == 1
    assert results[0].pk == user.pk


async def test_filter_with_or_two():
    await User.query.create(name="Adam")
    await User.query.create(name="Saffier")

    results = await User.query.filter(
        or_(User.columns.name == "Adam", User.columns.name == "Saffier")
    )

    assert len(results) == 2


async def test_filter_with_or_three():
    await User.query.create(name="Adam")
    user = await User.query.create(name="Saffier", email="saffier@saffier.dev")

    results = await User.query.filter(
        or_(User.columns.name == "Adam", User.columns.email == user.email)
    )

    assert len(results) == 2


async def test_filter_with_or_four():
    await User.query.create(name="Adam")
    user = await User.query.create(name="Saffier", email="saffier@saffier.dev")

    results = await User.query.filter(or_(User.columns.name == user.name)).filter(
        or_(User.columns.email == user.email)
    )
    assert len(results) == 1


async def test_filter_with_contains():
    await User.query.create(name="Adam", email="adam@saffier.dev")
    await User.query.create(name="Saffier", email="saffier@saffier.dev")

    results = await User.query.filter(or_(User.columns.email.contains("saffier")))
    assert len(results) == 2


async def test_filter_or_clause_style_nested():
    user = await User.query.create(name="Adam", email="adam@saffier.dev")
    await User.query.create(name="Saffier", email="saffier@saffier.dev")

    results = await User.query.or_(name="Adam").or_(email__icontains=user.email)

    assert len(results) == 1
    assert results[0].pk == user.pk

    results = await User.query.or_(email__icontains="saffier")

    assert len(results) == 2


async def test_filter_or_clause_related():
    user = await User.query.create(name="Adam", email="adam@saffier.dev")
    await User.query.create(name="Saffier", email="saffier@saffier.dev")
    product = await Product.query.create(user=user)

    results = await Product.query.or_(user__id=user.pk)

    assert len(results) == 1
    assert results[0].pk == product.pk

    results = await User.query.or_(products__id=product.pk)

    assert len(results) == 1
    assert results[0].pk == user.pk


async def test_filter_or_clause_select():
    user = await User.query.create(name="Adam", email="adam@saffier.dev")
    await User.query.create(name="Saffier", email="adam@saffier.dev")

    results = await User.query.or_(name="Test").or_(name="Adam")

    assert len(results) == 1
    assert results[0].pk == user.pk

    results = await User.query.or_(name="Saffier").or_(name="Adam")

    assert len(results) == 2


async def test_filter_or_clause_mixed():
    user = await User.query.create(name="Adam", email="adam@saffier.dev")
    await User.query.create(name="Saffier", email="adam@saffier.dev")

    results = await User.query.or_(name="Adam", email=user.email).and_(id=1)

    assert len(results) == 1
    assert results[0].pk == user.pk
