import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class Base(saffier.StrictModel):
    class Meta:
        abstract = True
        registry = models


class Profile(Base):
    name = saffier.CharField(max_length=1000)
    computed = saffier.ComputedField(
        getter=lambda field, model_instance, model_class: "foo",
    )


class User(Base):
    id = saffier.BigIntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=50, exclude=True)
    email = saffier.EmailField(max_length=100)
    password = saffier.CharField(max_length=1000, exclude=True)
    profile = saffier.ForeignKey(Profile, on_delete=saffier.CASCADE)


class Organisation(Base):
    user = saffier.ForeignKey(User)


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


async def seed_data():
    profile = await Profile.query.create(name="edgy")
    user = await User.query.create(
        profile=profile, email="user@dev.com", password="dasrq3213", name="edgy"
    )
    return await Organisation.query.create(user=user)


async def test_nested_with_not_optimal_select_related_exclude_secrets():
    await seed_data()

    org_query = Organisation.query.exclude_secrets(True)
    org_query._select_related = ["user", "user", "user__profile"]
    assert org_query._cached_select_related_expression is None
    org = await org_query.last()
    assert org_query._cached_select_related_expression is not None

    assert org.model_dump() == {
        "user": {"id": 1, "profile": {"id": 1, "name": "edgy"}, "email": "user@dev.com"},
        "id": 1,
    }


async def test_nested_with_not_optimal_select_related_defer():
    await seed_data()

    org_query = Organisation.query.defer("name")
    org_query._select_related = ["user", "user", "user__profile"]
    assert org_query._cached_select_related_expression is None
    org = await org_query.last()
    assert org_query._cached_select_related_expression is not None

    assert org.model_dump() == {
        "user": {"id": 1, "profile": {"id": 1, "name": "edgy"}, "email": "user@dev.com"},
        "id": 1,
    }


async def test_nested_with_not_optimal_select_related_all():
    await seed_data()

    org_query = Organisation.query.all()
    org_query._select_related = ["user", "user", "user__profile"]
    assert org_query._cached_select_related_expression is None
    org = await org_query.get()
    assert org_query._cached_select_related_expression is not None

    assert org.model_dump() == {
        "user": {"id": 1, "profile": {"id": 1, "name": "edgy"}, "email": "user@dev.com"},
        "id": 1,
    }
