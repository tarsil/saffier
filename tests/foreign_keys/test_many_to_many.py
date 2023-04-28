import pytest

import saffier
from saffier.exceptions import RelationshipIncompatible, RelationshipNotFound
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Track(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    title = saffier.CharField(max_length=100)
    position = saffier.IntegerField()

    class Meta:
        registry = models


class Album(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)
    tracks = saffier.ManyToManyField(Track)

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


async def test_add_many_to_many():
    track1 = await Track.query.create(title="The Bird", position=1)
    track2 = await Track.query.create(title="Heart don't stand a chance", position=2)
    track3 = await Track.query.create(title="The Waters", position=3)

    album = await Album.query.create(name="Malibu")

    await album.tracks.add(track1)
    await album.tracks.add(track2)
    await album.tracks.add(track3)

    total_tracks = await album.tracks.all()

    assert len(total_tracks) == 3


async def test_add_many_to_many_with_repeated_field():
    track1 = await Track.query.create(title="The Bird", position=1)
    track2 = await Track.query.create(title="Heart don't stand a chance", position=2)
    track3 = await Track.query.create(title="The Waters", position=3)

    album = await Album.query.create(name="Malibu")

    await album.tracks.add(track1)
    await album.tracks.add(track1)
    await album.tracks.add(track2)
    await album.tracks.add(track3)

    total_tracks = await album.tracks.all()

    assert len(total_tracks) == 3


async def test_delete_object_reflect_on_many_to_many():
    track1 = await Track.query.create(title="The Bird", position=1)
    track2 = await Track.query.create(title="Heart don't stand a chance", position=2)
    track3 = await Track.query.create(title="The Waters", position=3)

    album = await Album.query.create(name="Malibu")

    await album.tracks.add(track1)
    await album.tracks.add(track2)
    await album.tracks.add(track3)

    total_tracks = await album.tracks.all()

    assert len(total_tracks) == 3

    await track1.delete()

    total_tracks = await album.tracks.all()

    assert len(total_tracks) == 2


async def test_delete_child_from_many_to_many():
    track1 = await Track.query.create(title="The Bird", position=1)
    track2 = await Track.query.create(title="Heart don't stand a chance", position=2)
    track3 = await Track.query.create(title="The Waters", position=3)

    album = await Album.query.create(name="Malibu")

    await album.tracks.add(track1)
    await album.tracks.add(track2)
    await album.tracks.add(track3)

    total_album_tracks = await album.tracks.all()

    assert len(total_album_tracks) == 3

    await album.tracks.remove(track1)

    total_album_tracks = await album.tracks.all()

    assert len(total_album_tracks) == 2

    total_tracks = await Track.query.all()

    assert len(total_tracks) == 3


async def test_raises_RelationshipIncompatible():
    user = await User.query.create(name="Saffier")

    album = await Album.query.create(name="Malibu")

    with pytest.raises(RelationshipIncompatible) as raised:
        await album.tracks.add(user)

    assert raised.value.args[0] == "The child is not from the type 'Track'."


async def test_raises_RelationshipNotFound():
    track1 = await Track.query.create(title="The Bird", position=1)
    track2 = await Track.query.create(title="Heart don't stand a chance", position=2)
    track3 = await Track.query.create(title="The Waters", position=3)

    album = await Album.query.create(name="Malibu")

    await album.tracks.add(track1)
    await album.tracks.add(track2)

    with pytest.raises(RelationshipNotFound) as raised:
        await album.tracks.remove(track3)

    assert (
        raised.value.args[0]
        == f"There is no relationship between 'album' and 'track: {track3.pk}'."
    )
