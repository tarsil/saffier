import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class Base(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    class Meta:
        abstract = True
        registry = models


class User(Base):
    name = saffier.CharField(max_length=50)
    email = saffier.EmailField(max_length=100)
    password = saffier.CharField(max_length=1000, secret=True)


class Profile(Base):
    is_valid = saffier.BooleanField(default=True)
    access = saffier.CharField(max_length=255, secret=True)


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


async def test_exclude_secrets_query():
    await User.query.create(email="user@dev.com", password="dasrq3213", name="saffier")

    user = await User.query.exclude_secrets(id=1).get()

    assert user.pk == 1
    assert user.__dict__ == {"id": 1, "name": "saffier", "email": "user@dev.com"}


async def test_exclude_secrets():
    await Profile.query.create(access="admin")

    profile = await Profile.query.exclude_secrets(id=1).get()

    assert profile.pk == 1
    assert profile.model_dump() == {"id": 1, "is_valid": True}

    profile.access  # noqa

    assert profile.model_dump() == {"id": 1, "is_valid": True, "access": "admin"}

    profile = await Profile.query.exclude_secrets(id=1).get()

    assert profile.model_dump() == {"id": 1, "is_valid": True}
