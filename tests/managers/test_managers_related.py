from typing import ClassVar

import pytest

import saffier
from saffier import Manager
from saffier.core.db.querysets.base import QuerySet
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class InactiveManager(Manager):
    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(is_active=False)


class Team(saffier.StrictModel):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class User(saffier.StrictModel):
    name = saffier.CharField(max_length=255)
    email = saffier.EmailField(max_length=70)
    team = saffier.ForeignKey(Team, null=True, related_name="members")
    is_active = saffier.BooleanField(default=True)

    query_related: ClassVar[Manager] = InactiveManager()

    class Meta:
        registry = models
        unique_together = [("name", "email")]


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


async def test_managers_related():
    team = await Team.query.create(name="Saffier team")

    user1 = await User.query.create(
        name="Saffier", email="foo@bar.com", is_active=False, team=team
    )
    user2 = await User.query_related.create(
        name="Another Saffier", email="bar@foo.com", is_active=False, team=team
    )
    user3 = await User.query.create(name="Saffier", email="user@saffier.com", team=team)

    users = await User.query.all()
    assert [user1, user2, user3] == users

    members = await team.members.all()
    assert [user1, user2] == members
