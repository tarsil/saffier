import random
import string

import pytest

import saffier
from saffier.db.datastructures import Index
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL)
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


class ReflectedUser(saffier.ReflectModel):
    name = saffier.CharField(max_length=255)
    title = saffier.CharField(max_length=255, null=True)
    description = saffier.CharField(max_length=255, null=True)

    class Meta:
        tablename = "hubusers"
        registry = models


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


async def test_can_reflect_existing_table():
    await HubUser.query.create(name="Test", title="a title", description="desc")

    users = await ReflectedUser.query.all()

    assert len(users) == 1


async def test_can_reflect_and_edit_existing_table():
    await HubUser.query.create(name="Test", title="a title", description="desc")

    users = await ReflectedUser.query.all()

    assert len(users) == 1

    user = users[0]

    await user.update(name="Saffier", description="updated")

    users = await ReflectedUser.query.all()

    assert len(users) == 1

    user = users[0]

    assert user.name == "Saffier"
    assert user.description == "updated"

    users = await HubUser.query.all()

    assert len(users) == 1

    assert user.name == "Saffier"
    assert user.description == "updated"
