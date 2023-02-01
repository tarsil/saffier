import pytest
from tests.settings import DATABASE_URL

import saffier
from saffier.core import fields
from saffier.core.db import Database
from saffier.exceptions import DoesNotFound, MultipleObjectsReturned

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class User(saffier.Model):
    registry = models
    fields = {
        "id": saffier.IntegerField(primary_key=True),
        "name": saffier.CharField(max_length=100),
        "language": saffier.CharField(max_length=200, null=True),
    }


class Product(saffier.Model):
    tablename = "products"
    registry = models
    fields = {
        "id": saffier.IntegerField(primary_key=True),
        "name": saffier.CharField(max_length=100),
        "rating": saffier.IntegerField(minimum=1, maximum=5),
        "in_stock": saffier.BooleanField(default=False),
    }


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


def test_model_class():
    assert list(User.fields.keys()) == ["id", "name", "language"]
    assert isinstance(User.fields["id"], saffier.IntegerField)
    assert User.fields["id"].primary_key is True
    assert isinstance(User.fields["name"], saffier.CharField)
    assert User.fields["name"].validator.max_length == 100

    with pytest.raises(ValueError):
        User(invalid="123")

    assert User(id=1) != Product(id=1)
    assert User(id=1) != User(id=2)
    assert User(id=1) == User(id=1)

    assert str(User(id=1)) == "User(id=1)"
    assert repr(User(id=1)) == "<User: User(id=1)>"

    assert isinstance(User.query.schema.fields["id"], fields.Integer)
    assert isinstance(User.query.schema.fields["name"], fields.String)


def test_model_pk():
    user = User(pk=1)
    assert user.pk == 1
    assert user.id == 1
    assert User.query.pkname == "id"


async def test_model_crud():
    users = await User.query.all()
    assert users == []

    user = await User.query.create(name="Test")
    users = await User.query.all()
    assert user.name == "Test"
    assert user.pk is not None
    assert users == [user]

    lookup = await User.query.get()
    assert lookup == user

    await user.update(name="Jane")
    users = await User.query.all()
    assert user.name == "Jane"
    assert user.pk is not None
    assert users == [user]

    await user.delete()
    users = await User.query.all()
    assert users == []


async def test_model_get():
    with pytest.raises(DoesNotFound):
        await User.query.get()

    user = await User.query.create(name="Test")
    lookup = await User.query.get()
    assert lookup == user

    user = await User.query.create(name="Jane")
    with pytest.raises(MultipleObjectsReturned):
        await User.query.get()

    same_user = await User.query.get(pk=user.id)
    assert same_user.id == user.id
    assert same_user.pk == user.pk


async def test_model_filter():
    await User.query.create(name="Test")
    await User.query.create(name="Jane")
    await User.query.create(name="Lucy")

    user = await User.query.get(name="Lucy")
    assert user.name == "Lucy"

    with pytest.raises(DoesNotFound):
        await User.query.get(name="Jim")

    await Product.query.create(name="T-Shirt", rating=5, in_stock=True)
    await Product.query.create(name="Dress", rating=4)
    await Product.query.create(name="Coat", rating=3, in_stock=True)

    product = await Product.query.get(name__iexact="t-shirt", rating=5)
    assert product.pk is not None
    assert product.name == "T-Shirt"
    assert product.rating == 5

    products = await Product.query.all(rating__gte=2, in_stock=True)
    assert len(products) == 2

    products = await Product.query.all(name__icontains="T")
    assert len(products) == 2

    # Test escaping % character from icontains, contains, and iexact
    await Product.query.create(name="100%-Cotton", rating=3)
    await Product.query.create(name="Cotton-100%-Egyptian", rating=3)
    await Product.query.create(name="Cotton-100%", rating=3)
    products = Product.query.filter(name__iexact="100%-cotton")
    assert await products.count() == 1

    products = Product.query.filter(name__contains="%")
    assert await products.count() == 3

    products = Product.query.filter(name__icontains="%")
    assert await products.count() == 3

    products = Product.query.exclude(name__iexact="100%-cotton")
    assert await products.count() == 5

    products = Product.query.exclude(name__contains="%")
    assert await products.count() == 3

    products = Product.query.exclude(name__icontains="%")
    assert await products.count() == 3


async def test_model_order_by():
    await User.query.create(name="Bob")
    await User.query.create(name="Allen")
    await User.query.create(name="Bob")

    users = await User.query.order_by("name").all()
    assert users[0].name == "Allen"
    assert users[1].name == "Bob"

    users = await User.query.order_by("-name").all()
    assert users[1].name == "Bob"
    assert users[2].name == "Allen"

    users = await User.query.order_by("name", "-id").all()
    assert users[0].name == "Allen"
    assert users[0].id == 2
    assert users[1].name == "Bob"
    assert users[1].id == 3

    users = await User.query.filter(name="Bob").order_by("-id").all()
    assert users[0].name == "Bob"
    assert users[0].id == 3
    assert users[1].name == "Bob"
    assert users[1].id == 1

    users = await User.query.order_by("id").limit(1).all()
    assert users[0].name == "Bob"
    assert users[0].id == 1

    users = await User.query.order_by("id").limit(1).limit_offset(1).all()
    assert users[0].name == "Allen"
    assert users[0].id == 2


async def test_model_exists():
    await User.query.create(name="Test")
    assert await User.query.filter(name="Test").exists() is True
    assert await User.query.filter(name="Jane").exists() is False


async def test_model_count():
    await User.query.create(name="Test")
    await User.query.create(name="Jane")
    await User.query.create(name="Lucy")

    assert await User.query.count() == 3
    assert await User.query.filter(name__icontains="T").count() == 1


async def test_model_limit():
    await User.query.create(name="Test")
    await User.query.create(name="Jane")
    await User.query.create(name="Lucy")

    assert len(await User.query.limit(2).all()) == 2


async def test_model_limit_with_filter():
    await User.query.create(name="Test")
    await User.query.create(name="Test")
    await User.query.create(name="Test")

    assert len(await User.query.limit(2).filter(name__iexact="Test").all()) == 2


async def test_offset():
    await User.query.create(name="Test")
    await User.query.create(name="Jane")

    users = await User.query.limit_offset(1).limit(1).all()
    assert users[0].name == "Jane"


async def test_model_first():
    Test = await User.query.create(name="Test")
    jane = await User.query.create(name="Jane")

    assert await User.query.first() == Test
    assert await User.query.first(name="Jane") == jane
    assert await User.query.filter(name="Jane").first() == jane
    assert await User.query.filter(name="Lucy").first() is None


async def test_model_search():
    Test = await User.query.create(name="Test", language="English")
    tshirt = await Product.query.create(name="T-Shirt", rating=5)

    assert await User.query.search(term="").first() == Test
    assert await User.query.search(term="Test").first() == Test
    assert await Product.query.search(term="shirt").first() == tshirt


async def test_model_get_or_create():
    user, created = await User.query.get_or_create(
        name="Test", defaults={"language": "Portuguese"}
    )
    assert created is True
    assert user.name == "Test"
    assert user.language == "Portuguese"

    user, created = await User.query.get_or_create(name="Test", defaults={"language": "English"})
    assert created is False
    assert user.name == "Test"
    assert user.language == "Portuguese"


async def test_queryset_delete():
    shirt = await Product.query.create(name="Shirt", rating=5)
    await Product.query.create(name="Belt", rating=5)
    await Product.query.create(name="Tie", rating=5)

    await Product.query.filter(pk=shirt.id).delete()
    assert await Product.query.count() == 2

    await Product.query.delete()
    assert await Product.query.count() == 0


async def test_queryset_update():
    shirt = await Product.query.create(name="Shirt", rating=5)
    tie = await Product.query.create(name="Tie", rating=5)

    await Product.query.filter(pk=shirt.id).update(rating=3)
    shirt = await Product.query.get(pk=shirt.id)
    assert shirt.rating == 3
    assert await Product.query.get(pk=tie.id) == tie

    await Product.query.update(rating=3)
    tie = await Product.query.get(pk=tie.id)
    assert tie.rating == 3


async def test_model_update_or_create():
    user, created = await User.query.update_or_create(
        name="Test", language="English", defaults={"name": "Jane"}
    )
    assert created is True
    assert user.name == "Jane"
    assert user.language == "English"

    user, created = await User.query.update_or_create(
        name="Jane", language="English", defaults={"name": "Test"}
    )
    assert created is False
    assert user.name == "Test"
    assert user.language == "English"


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
