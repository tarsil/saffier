import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=200, null=True)

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


async def test_bulk_get_or_create_creates_all_without_unique_fields():
    users = await User.query.bulk_get_or_create(
        [
            {"name": "Alice", "language": "English"},
            {"name": "Bob", "language": "Portuguese"},
        ]
    )

    assert len(users) == 2
    assert await User.query.count() == 2


async def test_bulk_get_or_create_respects_unique_fields():
    existing = await User.query.create(name="Alice", language="English")

    users = await User.query.bulk_get_or_create(
        [
            {"name": "Alice", "language": "English"},
            {"name": "Bob", "language": "Portuguese"},
            {"name": "Bob", "language": "Portuguese"},
        ],
        unique_fields=["name", "language"],
    )

    assert len(users) == 2
    assert {user.name for user in users} == {"Alice", "Bob"}
    assert any(user.pk == existing.pk for user in users)
    assert await User.query.count() == 2


async def test_bulk_get_or_create_accepts_model_instances():
    users = await User.query.bulk_get_or_create(
        [
            User(name="Carol", language="French"),
            User(name="Carol", language="French"),
            User(name="Dora", language="German"),
        ],
        unique_fields=["name", "language"],
    )

    assert len(users) == 2
    assert {user.name for user in users} == {"Carol", "Dora"}
