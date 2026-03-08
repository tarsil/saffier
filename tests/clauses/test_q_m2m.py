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


class Role(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Category(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Product(saffier.Model):
    name = saffier.CharField(max_length=100)
    role = saffier.ForeignKey(Role, null=True)
    categories = saffier.ManyToManyField(Category)

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


async def test_q_m2m_simple_or_on_products():
    adam = await User.query.create(name="Adam", email="adam@saffier.dev")
    bob = await User.query.create(name="Bob", email="bob@example.com")

    soap = await Product.query.create(name="soap")
    potatos = await Product.query.create(name="potatos")
    other = await Product.query.create(name="other")

    await adam.products.add_many(soap, potatos)
    await bob.products.add(other)

    expression = Q(products__name__icontains="soap") | Q(products__name__icontains="potatos")

    results = await User.query.filter(expression).distinct("id")

    assert {user.pk for user in results} == {adam.pk}


async def test_q_m2m_nested_role_lookup():
    adam = await User.query.create(name="Adam", email="adam@saffier.dev")
    bob = await User.query.create(name="Bob", email="bob@example.com")

    shelf = await Role.query.create(name="shelf")
    other_role = await Role.query.create(name="floor")

    product = await Product.query.create(name="soap", role=shelf)
    other_product = await Product.query.create(name="potatos", role=other_role)

    await adam.products.add(product)
    await bob.products.add(other_product)

    results = await User.query.filter(Q(products__role__name__icontains="shelf")).distinct("id")

    assert {user.pk for user in results} == {adam.pk}


async def test_q_m2m_multi_hop_categories():
    adam = await User.query.create(name="Adam", email="adam@saffier.dev")
    bob = await User.query.create(name="Bob", email="bob@example.com")

    food = await Category.query.create(name="food")
    tools = await Category.query.create(name="tools")

    product = await Product.query.create(name="soap")
    other_product = await Product.query.create(name="hammer")

    await product.categories.add(food)
    await other_product.categories.add(tools)

    await adam.products.add(product)
    await bob.products.add(other_product)

    results = await User.query.filter(Q(products__categories__name="food")).distinct("id")

    assert {user.pk for user in results} == {adam.pk}


async def test_q_m2m_nested_q_tree():
    adam = await User.query.create(name="Adam", email="adam@saffier.dev")
    other_user = await User.query.create(name="Other", email="other@example.com")

    shelf = await Role.query.create(name="shelf")
    other_role = await Role.query.create(name="floor")

    soap = await Product.query.create(name="soap", role=shelf)
    other_product = await Product.query.create(name="other", role=other_role)

    await adam.products.add(soap)
    await other_user.products.add(other_product)

    inner = Q(products__name__icontains="soap") | Q(products__role__name="shelf")
    expression = Q(inner) & Q(email__icontains="saffier")

    results = await User.query.filter(expression).distinct("id")

    assert {user.pk for user in results} == {adam.pk}


async def test_q_m2m_combined_with_user_fields():
    adam = await User.query.create(name="Adam", email="adam@saffier.dev")
    bob = await User.query.create(name="Adam", email="other@example.com")

    soap = await Product.query.create(name="soap")
    other_product = await Product.query.create(name="other")

    await adam.products.add(soap)
    await bob.products.add(other_product)

    expression = Q(name="Adam") & Q(products__name__icontains="soap")
    results = await User.query.filter(expression).distinct("id")

    assert {user.pk for user in results} == {adam.pk}


async def test_q_m2m_equivalence_to_or_chain():
    adam = await User.query.create(name="Adam", email="adam@saffier.dev")
    bob = await User.query.create(name="Bob", email="bob@example.com")

    soap = await Product.query.create(name="soap")
    potatos = await Product.query.create(name="potatos")
    other = await Product.query.create(name="other")

    await adam.products.add_many(soap, potatos)
    await bob.products.add(other)

    expression = Q(products__name__icontains="soap") | Q(products__name__icontains="potatos")
    q_results = await User.query.filter(expression).distinct("id")

    chain_results = await (
        User.query.or_(products__name__icontains="soap")
        .or_(products__name__icontains="potatos")
        .distinct("id")
    )

    assert {user.pk for user in q_results} == {user.pk for user in chain_results}
