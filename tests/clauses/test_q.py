import pytest

import saffier
from saffier.core.db.querysets.clauses import Q
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


async def test_q_and_operator_with_kwargs():
    user = await User.query.create(name="Adam", email="adam@saffier.dev")
    await User.query.create(name="Adam", email="adam@other.dev")

    expression = Q(name="Adam") & Q(email__icontains="saffier")
    results = await User.query.filter(expression)

    assert len(results) == 1
    assert results[0].pk == user.pk


async def test_q_or_operator_with_kwargs():
    adam = await User.query.create(name="Adam", email="adam@saffier.dev")
    other = await User.query.create(name="Saffier", email="saffier@saffier.dev")
    await User.query.create(name="Third", email="third@example.com")

    expression = Q(name="Adam") | Q(name="Saffier")
    results = await User.query.filter(expression)

    assert {user.pk for user in results} == {adam.pk, other.pk}


async def test_q_not_operator_with_kwargs():
    await User.query.create(name="Adam", email="adam@saffier.dev")
    user = await User.query.create(name="Saffier", email="saffier@saffier.dev")

    expression = ~Q(name="Adam")
    results = await User.query.filter(expression)

    assert len(results) == 1
    assert results[0].pk == user.pk


async def test_q_with_raw_clause():
    user = await User.query.create(name="Adam", email="adam@saffier.dev")
    await User.query.create(name="Saffier", email="saffier@saffier.dev")

    expression = Q(User.columns.name == "Adam") & Q(User.columns.email == "adam@saffier.dev")
    results = await User.query.filter(expression)

    assert len(results) == 1
    assert results[0].pk == user.pk


async def test_q_nested_q_objects():
    user = await User.query.create(name="Adam", email="adam@saffier.dev", language="EN")
    await User.query.create(name="Adam", email="adam@saffier.dev", language="PT")

    inner = Q(name="Adam", email__icontains="saffier")
    expression = Q(inner) & Q(language="EN")
    results = await User.query.filter(expression)

    assert len(results) == 1
    assert results[0].pk == user.pk


async def test_q_with_related_fields():
    user = await User.query.create(name="Adam", email="adam@saffier.dev")
    product = await Product.query.create(user=user, name="soap")

    expression = Q(user__id=user.pk) & Q(name="soap")
    results = await Product.query.filter(expression)

    assert len(results) == 1
    assert results[0].pk == product.pk


async def test_q_inside_or_operator():
    adam = await User.query.create(name="Adam", email="adam@saffier.dev")
    saffier_user = await User.query.create(name="Saffier", email="saffier@saffier.dev")

    results = await User.query.or_(Q(name="Adam")).or_(Q(name="Saffier"))

    assert {user.pk for user in results} == {adam.pk, saffier_user.pk}
