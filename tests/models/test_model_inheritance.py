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
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=200, null=True)

    class Meta:
        registry = models


class Profile(User):
    age = saffier.IntegerField()

    class Meta:
        registry = models
        name = "profiles"


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


async def test_model_inheritance():
    user = await User.query.create(name="Test", language="EN")
    profile = await Profile.query.create(name="Test2", language="PT", age=25)

    users = await User.query.all()
    profiles = await Profile.query.all()

    assert len(users) == 1
    assert len(profiles) == 1
