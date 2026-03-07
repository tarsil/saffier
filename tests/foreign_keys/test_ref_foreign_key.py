import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class Team(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    slug = saffier.CharField(max_length=100, unique=True)

    class Meta:
        registry = models


class Member(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)
    team = saffier.RefForeignKey(Team, on_delete=saffier.CASCADE, ref_field="slug")

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connection():
    with database.force_rollback():
        async with database:
            yield


async def test_ref_foreign_key_behaves_like_foreign_key_with_reference_metadata():
    assert isinstance(Member.fields["team"], saffier.ForeignKey)
    assert Member.fields["team"].ref_field == "slug"

    team = await Team.query.create(slug="eng")
    member = await Member.query.create(name="Alice", team=team)
    loaded = await Member.query.get(pk=member.pk)

    assert loaded.team.pk == team.pk
