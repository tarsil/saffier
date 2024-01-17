import pytest

import saffier
from saffier.exceptions import QuerySetError
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Post(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    user = saffier.ForeignKey(User, related_name="posts")
    comment = saffier.CharField(max_length=255)

    class Meta:
        registry = models


class Article(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    user = saffier.ForeignKey(User, related_name="articles")
    content = saffier.CharField(max_length=255)

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


class Test:
    ...


async def test_raise_prefetch_related_error():
    await User.query.create(name="Saffier")

    with pytest.raises(QuerySetError):
        await User.query.prefetch_related(
            Test(),
        ).all()
