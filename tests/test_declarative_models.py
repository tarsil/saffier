import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(DATABASE_URL)
models = saffier.Registry(database=saffier.Database(database, force_rollback=True))

pytestmark = pytest.mark.anyio


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100, null=True)
    language = saffier.CharField(max_length=200, null=True)

    class Meta:
        registry = models


class Profile(saffier.Model):
    user = saffier.ForeignKey(User)

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    async with database:
        await models.create_all()
        yield
        if not database.drop:
            await models.drop_all()


@pytest.fixture(autouse=True, scope="function")
async def rollback_transactions():
    async with models:
        yield


async def test_model_declarative_with_relationship():
    user = await User.query.create()
    profile = await Profile.query.create(user=user)
    declarative_profile = Profile.declarative()

    assert hasattr(declarative_profile, "user_relation")
    assert not hasattr(profile, "user_relation")
