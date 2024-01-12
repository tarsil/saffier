import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class Base(saffier.Model):
    class Meta:
        abstract = True
        registry = models


class Profile(Base):
    is_enabled = saffier.BooleanField(default=True, secret=True)
    name = saffier.CharField(max_length=1000, secret=True)


class User(Base):
    name = saffier.CharField(max_length=50)
    email = saffier.EmailField(max_length=100)
    password = saffier.CharField(max_length=1000, secret=True)
    profile = saffier.ForeignKey(Profile, on_delete=saffier.CASCADE)


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
    profile = await Profile.query.create(is_enabled=False, name="saffier")
    await User.query.create(
        profile=profile, email="user@dev.com", password="dasrq3213", name="saffier"
    )

    user = await User.query.exclude_secrets(id=1).get()

    assert user.pk == 1
