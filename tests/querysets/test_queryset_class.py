import pytest

import saffier
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL)
models = saffier.Registry(database=database)


class User(saffier.StrictModel):
    name = saffier.CharField(max_length=100, null=True)

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True, scope="function")
async def rollback_transactions():
    with database.force_rollback():
        async with database:
            yield


async def test_queryset_cache_all():
    users = await User.query.all()
    assert users == []

    user = await User.query.create(name="Test")
    query = User.query.all()
    query2 = query.all()

    assert query._cached_select_with_tables is None
    assert await query == [user]
    assert query._cache_fetch_all
    assert query._cached_select_with_tables is not None

    await query2
    await query2.create(name="Test2")

    assert await query == [user]
    assert await query.get() is (await query)[0]

    assert len(await query2) == 2

    query.all(True)
    assert query._cached_select_with_tables is not None

    returned_list = await query
    assert returned_list[0] is not user
    assert len(returned_list) == 2


async def test_queryset_cache_get():
    users = await User.query.all()
    assert users == []

    query = User.query.filter(name="Test")
    user = await query.create(name="Test")

    assert query._cache.cache
    assert user is await query.get()
