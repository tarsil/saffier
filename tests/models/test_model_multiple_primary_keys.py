import pytest

import saffier
from saffier import Registry
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL, full_isolation=False)
models = Registry(database=database)


class User(saffier.StrictModel):
    non_default_id = saffier.BigIntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100, primary_key=True)
    language = saffier.CharField(max_length=200, null=True)
    parent = saffier.ForeignKey(
        "User", on_delete=saffier.SET_NULL, null=True, related_name="children"
    )

    class Meta:
        registry = models
        tablename = "composite_users"


@pytest.fixture(autouse=True, scope="function")
async def create_test_database():
    async with database:
        await models.create_all()
        yield
        if not database.drop:
            await models.drop_all()


async def test_model_multiple_primary_key():
    user = await User.query.create(language="EN", name="edgy")

    assert user.non_default_id == 1
    assert user.name == "edgy"
    assert user.pk == {"non_default_id": 1, "name": "edgy"}
    users = await User.query.filter()
    assert len(users) == 1

    user2 = await User.query.create(language="DE", name="edgy2", parent=user)
    assert user2.name == "edgy2"
    assert user2.pk == {"non_default_id": 2, "name": "edgy2"}
    assert user2.parent.pk == {"non_default_id": 1, "name": "edgy"}
    assert await User.query.filter(parent=user).count() == 1

    loaded = await User.query.get(non_default_id=2, name="edgy2")
    assert loaded.parent.pk == {"non_default_id": 1, "name": "edgy"}
    await loaded.parent.load()
    assert loaded.parent.language == "EN"

    selected = await User.query.select_related("parent").get(non_default_id=2, name="edgy2")
    assert selected.parent.pk == {"non_default_id": 1, "name": "edgy"}
    assert selected.parent.language == "EN"

    users = await User.query.filter()
    assert len(users) == 2


async def test_model_multiple_primary_key_explicit_id():
    user = await User.query.create(language="EN", name="edgy", non_default_id=45)

    assert user.non_default_id == 45
    assert user.name == "edgy"
    assert user.pk == {"non_default_id": 45, "name": "edgy"}
    users = await User.query.filter()
    assert len(users) == 1

    user2 = await User.query.create(language="DE", name="edgy2", parent=user)
    assert user2.name == "edgy2"
    assert user2.pk["name"] == "edgy2"
    assert user2.parent.pk == {"non_default_id": 45, "name": "edgy"}
    users = await User.query.filter()
    assert len(users) == 2


async def test_model_multiple_primary_key_idempotence():
    user = await User.query.create(language="EN", name="edgy")
    user2 = await User.query.create(language="EN", name="edgy2", parent=user)
    extracted_fields = user2.extract_db_fields()
    column_values = user2.extract_column_values(extracted_fields)
    assert User(**column_values).model_dump() == user2.model_dump(
        exclude={"parent": {"language": True}}
    )
