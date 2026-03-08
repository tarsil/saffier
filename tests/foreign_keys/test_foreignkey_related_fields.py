import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class RelatedAlbum(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    slug = saffier.CharField(max_length=100, unique=True)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        tablename = "related_albums"


class RelatedTrack(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    album = saffier.ForeignKey(
        "RelatedAlbum",
        on_delete=saffier.CASCADE,
        related_fields=("slug",),
        index=True,
    )
    title = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        tablename = "related_tracks"


class Organisation(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    ident = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        tablename = "related_orgs"


class Team(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    org = saffier.ForeignKey(Organisation, on_delete=saffier.RESTRICT, index=True)
    name = saffier.CharField(max_length=100, primary_key=True)

    class Meta:
        registry = models
        tablename = "related_teams"


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
        tablename = "related_members"


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


async def test_related_fields_follow_non_pk_unique_field():
    album = await RelatedAlbum.query.create(slug="malibu", name="Malibu")
    await RelatedTrack.query.create(album=album, title="The Bird")
    await RelatedTrack.query.create(album=album, title="The Waters")

    track = await RelatedTrack.query.select_related("album").get(title="The Bird")
    assert track.album.slug == "malibu"
    assert track.album.name == "Malibu"

    tracks = await RelatedTrack.query.filter(album__slug="malibu").all()
    assert len(tracks) == 2
    assert all(item.album.slug == "malibu" for item in tracks)


async def test_no_constraint_composite_fk_keeps_composite_pointer():
    organisation = await Organisation.query.create(ident="Encode")
    team = await Team.query.create(org=organisation, name="Maintainers")
    await Member.query.create(email="member@saffier.com", team=team)

    await team.delete()

    member = await Member.query.get()
    assert member.team is not None
    assert member.team.name == "Maintainers"
