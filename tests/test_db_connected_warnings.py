import warnings

import pytest

import saffier
from saffier.exceptions import DatabaseNotConnectedWarning
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL)
models = saffier.Registry(database=saffier.Database(database))


class User(saffier.StrictModel):
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=200, null=True)
    email = saffier.EmailField(null=True, max_length=255)

    class Meta:
        registry = models


class Product(saffier.StrictModel):
    user = saffier.ForeignKey(User, related_name="products")

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    async with database:
        await models.create_all()
        yield
        if not database.drop:
            await models.drop_all()


async def test_multiple_operations():
    with pytest.warns(DatabaseNotConnectedWarning):
        await User.query.create(name="Adam", language="EN")

    query = User.query.filter()

    with pytest.warns(DatabaseNotConnectedWarning):
        await query

    with pytest.warns(DatabaseNotConnectedWarning):
        await User.query.delete()


async def test_multiple_operations_user_warning():
    with pytest.warns(UserWarning):
        await User.query.create(name="Adam", language="EN")

    query = User.query.filter()

    with pytest.warns(UserWarning):
        await query

    with pytest.warns(UserWarning):
        await User.query.delete()


async def test_no_warning_manual_way():
    await models.__aenter__()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        await User.query.create(name="Adam", language="EN")
        await User.query.filter()
        await User.query.delete()
    await models.__aexit__()
