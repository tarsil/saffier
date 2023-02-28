import random
import string

import pytest
from tests.settings import DATABASE_URL

import saffier
from saffier.db.datastructures import Index
from saffier.testclient import DatabaseTestClient as Database

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


def get_random_string(length):
    letters = string.ascii_lowercase
    result_str = "".join(random.choice(letters) for i in range(length))
    return result_str


class User(saffier.Model):
    name = saffier.CharField(max_length=255, index=True)
    title = saffier.CharField(max_length=255, null=True)

    class Meta:
        registry = models
        indexes = [Index(fields=["name", "title"], name="idx_name_title")]


class HubUser(saffier.Model):
    name = saffier.CharField(max_length=255)
    title = saffier.CharField(max_length=255, null=True)
    description = saffier.CharField(max_length=255, null=True)

    class Meta:
        registry = models
        indexes = [
            Index(fields=["name", "title"], name="idx_title_name"),
            Index(fields=["name", "description"], name="idx_name_description"),
        ]


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_transactions():
    with database.force_rollback():
        async with database:
            yield


async def test_creates_index_for_table():
    await User.query.create(name="Test", title="a title")

    indexes = {value.name for value in User.table.indexes}

    assert "idx_name_title" in indexes


async def test_creates_multiple_index_for_table():
    await HubUser.query.create(name="Test", title="a title")

    indexes = {value.name for value in HubUser.table.indexes}

    assert "idx_name_description" in indexes
