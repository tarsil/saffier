from typing import Any

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
    description = saffier.TextField(max_length=5000, null=True)

    class Meta:
        registry = models


class Organisation(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    ident = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Team(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    org = saffier.ForeignKey(Organisation, on_delete=saffier.RESTRICT)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Member(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    team = saffier.ForeignKey(Team, on_delete=saffier.SET_NULL, null=True, related_name="members")
    second_team = saffier.ForeignKey(
        Team, on_delete=saffier.SET_NULL, null=True, related_name="team_members"
    )
    email = saffier.CharField(max_length=100)
    name = saffier.CharField(max_length=255, null=True)

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


async def test_model_fields_are_different():
    user: User = await User.query.create(name="John", language="PT", description="John")

    assert user.proxy_model.fields["name"].annotation == Any
    assert User.proxy_model.fields["name"].annotation == Any
