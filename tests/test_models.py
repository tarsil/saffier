import pytest
from core._internal import SaffierField
from tests.settings import DATABASE_URL

import saffier
from saffier.core.db import Database
from saffier.fields import CharField, IntegerField

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


# class Product(saffier.Model):
#     tablename = "products"
#     registry = models
#     fields = {
#         "id": saffier.IntegerField(primary_key=True),
#         "name": saffier.CharField(max_length=100),
#         "rating": saffier.IntegerField(minimum=1, maximum=5),
#         "in_stock": saffier.BooleanField(default=False),
#     }


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


# def test_model_class():
#     assert list(User.fields.keys()) == ["id", "name", "language"]
#     assert isinstance(User.fields["id"], saffier.IntegerField)
#     assert User.fields["id"].primary_key is True
#     assert isinstance(User.fields["name"], saffier.CharField)
#     assert User.fields["name"].validator.max_length == 100

#     with pytest.raises(ValueError):
#         User(invalid="123")

#     assert User(id=1) != Product(id=1)
#     assert User(id=1) != User(id=2)
#     assert User(id=1) == User(id=1)

#     assert str(User(id=1)) == "User(id=1)"
#     assert repr(User(id=1)) == "<User: User(id=1)>"

#     assert isinstance(User.query.schema.fields["id"], SaffierField)
#     assert isinstance(User.query.schema.fields["name"], SaffierField)


def test_model_pk():
    user = User(pk=1)
    assert user.pk == 1
    assert user.id == 1
    assert User.query.pkname == "id"


async def test_model_crud():
    users = await User.query.all()
    assert users == []

    breakpoint()
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
