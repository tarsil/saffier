import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


async def test_registry_get_model():
    assert models.get_model("User") is User


async def test_registry_context_manager_connects_and_disconnects():
    assert not models.database.is_connected
    async with models:
        assert models.database.is_connected
    assert not models.database.is_connected
