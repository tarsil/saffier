import pytest

import saffier
from saffier import Registry
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = Registry(database=database)
nother = Registry(database=database)

pytestmark = pytest.mark.anyio


class BaseUser(saffier.Model):
    id: int = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=200, null=True)

    class Meta:
        abstract = True


class Profile(BaseUser):
    age = saffier.IntegerField()

    class Meta:
        registry = models
        tablename = "profiles"


class Address(saffier.Model):
    id: int = saffier.IntegerField(primary_key=True)
    line_one = saffier.CharField(max_length=255, null=True)
    post_code = saffier.CharField(max_length=255, null=True)

    class Meta:
        registry = models
        tablename = "addresses"


class Contact(BaseUser, Address):
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
    await Profile.query.create(name="test", language="EN", age=23)
    await Address.query.create(line_one="teste")
    contact = await Contact.query.create(name="test2", language="AU", age=25, post_code="line")

    profiles = await Profile.query.all()
    addresses = await Address.query.all()
    contacts = await Contact.query.all()

    assert contact.post_code == "line"
    assert len(profiles) == 1
    assert len(addresses) == 1
    assert len(contacts) == 1
