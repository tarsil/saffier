import json

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
        table_prefix = "secret_toggle"


class Main(Base):
    name = saffier.CharField(max_length=255)


class User(Base):
    name = saffier.CharField(max_length=100)
    age = saffier.IntegerField(secret=True)
    language = saffier.CharField(max_length=200, null=True, secret=True)
    main = saffier.ForeignKey(Main, related_name="users", secret=True, null=True)


class RelatedUser(Base):
    first_name = saffier.CharField(max_length=255)
    last_name = saffier.CharField(max_length=255, secret=True)
    email = saffier.EmailField(max_length=255)


class Gratitude(Base):
    owner = saffier.ForeignKey(RelatedUser, related_name="gratitude")
    title = saffier.CharField(max_length=100)
    description = saffier.TextField()
    color = saffier.CharField(max_length=10, null=True)


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


async def test_exclude_secrets_can_be_undone():
    main = await Main.query.create(name="main")
    created = await User.query.create(name="Saffier", age=2, language="EN", main=main)

    user = await User.query.exclude_secrets().exclude_secrets(False).get(id=created.id)
    await user.load_recursive()

    expected = {
        "id": created.id,
        "name": "Saffier",
        "age": 2,
        "language": "EN",
        "main": {"id": main.id, "name": "main"},
    }

    assert user.model_dump() == expected
    assert json.loads(user.model_dump_json()) == expected


async def test_load_recursive_restores_secret_fields_after_secret_query():
    main = await Main.query.create(name="main")
    created = await User.query.create(name="Edgy", age=3, language="PT", main=main)

    user = await User.query.exclude_secrets().get(id=created.id)

    assert user.model_dump() == {"id": created.id, "name": "Edgy"}

    await user.load_recursive()

    assert user.model_dump() == {
        "id": created.id,
        "name": "Edgy",
        "age": 3,
        "language": "PT",
        "main": {"id": main.id, "name": "main"},
    }


async def test_exclude_secrets_masks_related_models():
    owner = await RelatedUser.query.create(
        first_name="Edgy",
        last_name="ORM",
        email="edgy@edgy.dev",
    )
    gratitude = await Gratitude.query.create(
        owner=owner,
        title="test",
        description="A desc",
        color="green",
    )

    result = await Gratitude.query.select_related("owner").exclude_secrets().get(id=gratitude.id)

    assert result.id == gratitude.id
    assert result.owner.model_dump() == {
        "id": owner.id,
        "first_name": "Edgy",
        "email": "edgy@edgy.dev",
    }
