import pytest

import saffier
from saffier import Registry
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = Registry(database=database)
nother = Registry(database=database)

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
        tablename = "profiles"


class Contact(Profile):
    id = saffier.IntegerField(primary_key=True)
    age = saffier.CharField(max_length=255)
    address = saffier.CharField(max_length=255)

    class Meta:
        registry = models
        tablename = "contacts"


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
    user = saffier.run_sync(User.query.create(name="Test", language="EN"))
    profile = saffier.run_sync(Profile.query.create(name="Test2", language="PT", age=23))

    users = saffier.run_sync(User.query.all())
    profiles = saffier.run_sync(Profile.query.all())

    assert len(users) == 1
    assert len(profiles) == 1
    assert users[0].pk == user.pk
    assert profiles[0].pk == profile.pk


async def test_model_triple_inheritace():
    contact = saffier.run_sync(
        Contact.query.create(name="Test", language="EN", age="25", address="Far")
    )

    contacts = saffier.run_sync(Contact.query.all())

    assert len(contacts) == 1
    assert contact.age == "25"
    assert contact.address == "Far"
