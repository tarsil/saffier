import pytest

import saffier
from saffier.exceptions import QuerySetError
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=200, null=True)
    description = saffier.TextField(max_length=5000, null=True)

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


async def test_model_values():
    saffier.run_sync(
        User.query.create(name="John", language="PT", description="A simple description")
    )
    saffier.run_sync(
        User.query.create(name="Jane", language="EN", description="Another simple description")
    )

    users = saffier.run_sync(User.query.values_list())

    assert len(users) == 2

    assert users == [
        (1, "John", "PT", "A simple description"),
        (2, "Jane", "EN", "Another simple description"),
    ]


async def test_model_values_list_fields():
    saffier.run_sync(User.query.create(name="John", language="PT"))
    saffier.run_sync(
        User.query.create(name="Jane", language="EN", description="Another simple description")
    )

    users = saffier.run_sync(User.query.values_list(["name"]))

    assert len(users) == 2

    assert users == [("John",), ("Jane",)]


async def test_model_values_list_flatten():
    saffier.run_sync(User.query.create(name="John", language="PT"))
    saffier.run_sync(
        User.query.create(name="Jane", language="EN", description="Another simple description")
    )

    users = saffier.run_sync(User.query.values_list(["name"], flat=True))

    assert len(users) == 2

    assert users == ["John", "Jane"]


@pytest.mark.parametrize(
    "value", [1, {"name": 1}, (1,), {"saffier"}], ids=["as-int", "as-dict", "as-tuple", "as-set"]
)
async def test_raise_exception(value):
    with pytest.raises(QuerySetError):
        saffier.run_sync(User.query.values_list(value))


async def test_raise_exception_on_flatten_non_field():
    saffier.run_sync(User.query.create(name="John", language="PT"))
    saffier.run_sync(
        User.query.create(name="Jane", language="EN", description="Another simple description")
    )

    users = saffier.run_sync(User.query.values_list(["name"], flat=True))

    assert len(users) == 2

    with pytest.raises(QuerySetError):
        saffier.run_sync(User.query.values_list("age", flat=True))


async def test_model_values_exclude_fields():
    saffier.run_sync(User.query.create(name="John", language="PT"))
    saffier.run_sync(
        User.query.create(name="Jane", language="EN", description="Another simple description")
    )

    users = saffier.run_sync(User.query.values_list(exclude=["name", "id"]))
    assert len(users) == 2

    assert users == [("PT", None), ("EN", "Another simple description")]


async def test_model_values_exclude_and_include_fields():
    saffier.run_sync(User.query.create(name="John", language="PT"))
    saffier.run_sync(
        User.query.create(name="Jane", language="EN", description="Another simple description")
    )

    users = saffier.run_sync(User.query.values_list(["id"], exclude=["name"]))
    assert len(users) == 2

    assert users == [(1,), (2,)]


async def test_model_values_exclude_none():
    saffier.run_sync(User.query.create(name="John", language="PT"))
    saffier.run_sync(
        User.query.create(name="Jane", language="EN", description="Another simple description")
    )

    users = saffier.run_sync(User.query.values_list(exclude_none=True))
    assert len(users) == 2

    assert users == [(1, "John", "PT"), (2, "Jane", "EN", "Another simple description")]


async def test_model_only_with_filter():
    saffier.run_sync(User.query.create(name="John", language="PT"))
    saffier.run_sync(
        User.query.create(name="Jane", language="EN", description="Another simple description")
    )

    users = saffier.run_sync(User.query.filter(id=2).values_list("name"))
    assert len(users) == 1

    assert users == [("Jane",)]

    users = saffier.run_sync(User.query.filter(id=3).values_list("name"))

    assert len(users) == 0

    assert users == []
