import json

import pytest

import saffier
from saffier.core.utils.db import hash_tablekey
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL, use_existing=False)
models = saffier.Registry(database=database)


class Base(saffier.StrictModel):
    class Meta:
        abstract = True
        registry = models


class Profile(Base):
    is_enabled = saffier.BooleanField(default=True, secret=True)
    name = saffier.CharField(max_length=1000)


class User(Base):
    name = saffier.CharField(max_length=50, secret=True)
    email = saffier.EmailField(max_length=100)
    password = saffier.CharField(max_length=1000, secret=True)
    profile = saffier.ForeignKey(Profile, on_delete=saffier.CASCADE)


class Organisation(Base):
    user = saffier.ForeignKey(User)


@pytest.fixture(autouse=True, scope="function")
async def create_test_database():
    async with models:
        await models.create_all()
        yield
        if not database.drop:
            await models.drop_all()


async def test_exclude_secrets_excludes_top_name_equals_to_name_in_foreignkey_not_secret_query():
    profile = await Profile.query.create(is_enabled=False, name="edgy")
    user = await User.query.create(
        profile=profile, email="user@dev.com", password="dasrq3213", name="edgy"
    )
    await Organisation.query.create(user=user)

    organisation_query = await (
        Organisation.query.select_related("user__profile").exclude_secrets().order_by("id")
    ).as_select()
    organisation_query_text = str(organisation_query)

    profile_alias = f'"{hash_tablekey(tablekey="profiles", prefix="user__profile")}".name'
    assert profile_alias in organisation_query_text or "profiles.name" in organisation_query_text
    assert (
        f'"{hash_tablekey(tablekey="users", prefix="user")}".name' not in organisation_query_text
    )


async def test_exclude_secrets_excludes_top_name_equals_to_name_in_foreignkey_not_secret():
    profile = await Profile.query.create(is_enabled=False, name="edgy")
    user = await User.query.create(
        profile=profile, email="user@dev.com", password="dasrq3213", name="edgy"
    )
    await Organisation.query.create(user=user)

    organisation = await (
        Organisation.query.select_related("user__profile").exclude_secrets().order_by("id")
    ).last()

    assert organisation.model_dump() == {
        "user": {"id": 1, "profile": {"id": 1, "name": "edgy"}, "email": "user@dev.com"},
        "id": 1,
    }

    assert json.loads(organisation.model_dump_json()) == {
        "user": {"id": 1, "profile": {"id": 1, "name": "edgy"}, "email": "user@dev.com"},
        "id": 1,
    }
