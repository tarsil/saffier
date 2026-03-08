import pytest

import saffier
from saffier.exceptions import RelationshipNotFound
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio
TABLE_PREFIX = "revrel"

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class Album(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        table_prefix = TABLE_PREFIX


class Track(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    album = saffier.ForeignKey(Album, on_delete=saffier.CASCADE, null=True)
    title = saffier.CharField(max_length=100)
    position = saffier.IntegerField()

    class Meta:
        registry = models
        table_prefix = TABLE_PREFIX


class Profile(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    website = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        table_prefix = TABLE_PREFIX


class Person(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    email = saffier.CharField(max_length=100)
    profile = saffier.OneToOneField(Profile, on_delete=saffier.CASCADE, null=True)

    class Meta:
        registry = models
        table_prefix = TABLE_PREFIX


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


async def test_reverse_fk_add_and_remove():
    track1 = await Track.query.create(title="The Bird", position=1)
    track2 = await Track.query.create(title="Heart don't stand a chance", position=2)
    album = await Album.query.create(name="Malibu")

    await album.tracks_set.add(track1)
    await album.tracks_set.add(track2)

    tracks = await album.tracks_set.order_by("position").all()
    assert [track.pk for track in tracks] == [track1.pk, track2.pk]

    await album.tracks_set.remove(track2)

    remaining = await album.tracks_set.all()
    assert [track.pk for track in remaining] == [track1.pk]
    await track2.load()
    assert track2.album.pk is None


async def test_reverse_fk_stage_on_create():
    track1 = await Track.query.create(title="The Bird", position=1)
    track2 = await Track.query.create(title="Heart don't stand a chance", position=2)

    album = await Album.query.create(name="Malibu", tracks_set=[track1, track2])
    tracks = await album.tracks_set.order_by("position").all()

    assert [track.pk for track in tracks] == [track1.pk, track2.pk]
    await track1.load()
    await track2.load()
    assert track1.album.pk == album.pk
    assert track2.album.pk == album.pk


async def test_reverse_fk_create():
    album = await Album.query.create(name="Malibu")

    first = await album.tracks_set.create(title="The Bird", position=1)
    second = await album.tracks_set.create(title="Heart don't stand a chance", position=2)

    tracks = await album.tracks_set.order_by("position").all()
    assert [track.pk for track in tracks] == [first.pk, second.pk]


async def test_one_to_one_default_related_name_is_singular_and_removable():
    assert "person" in Profile.meta.related_fields
    assert "persons_set" not in Profile.meta.related_fields

    profile = await Profile.query.create(website="https://saffier.com")
    person = await Person.query.create(email="info@saffier.com", profile=profile)

    related = await profile.person.get()
    assert related.pk == person.pk

    await profile.person.remove()

    await person.load()
    assert person.profile.pk is None


async def test_reverse_unique_relation_remove_without_child_raises_when_empty():
    profile = await Profile.query.create(website="https://saffier.com")

    with pytest.raises(RelationshipNotFound, match="No child found."):
        await profile.person.remove()
