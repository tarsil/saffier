import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class Team(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Member(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    team = saffier.ForeignKey(
        Team,
        on_delete=saffier.SET_NULL,
        null=True,
        no_constraint=True,
        index=True,
    )
    email = saffier.CharField(max_length=100)

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connections():
    with database.force_rollback():
        async with database:
            yield


async def test_deleting_parent_with_no_constraint_keeps_child_pointer():
    team = await Team.query.create(name="Maintainers")
    await Member.query.create(email="member@saffier.com", team=team)

    await team.delete()

    member = await Member.query.get()
    assert member.team.pk == team.pk
