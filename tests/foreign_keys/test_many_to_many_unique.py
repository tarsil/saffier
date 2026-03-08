import pytest

import saffier
from saffier.core.db.relationships import ManyRelation
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio
TABLE_PREFIX = "m2muniq"

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class Track(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    title = saffier.CharField(max_length=100)
    position = saffier.IntegerField()

    class Meta:
        registry = models
        table_prefix = TABLE_PREFIX


class Album(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)
    tracks = saffier.ManyToManyField(
        Track,
        embed_through="embedded",
        unique=True,
        index=True,
    )

    class Meta:
        registry = models
        table_prefix = TABLE_PREFIX


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


async def test_add_many_to_many_unique_succeeds():
    track1 = await Track.query.create(title="The Bird", position=1)
    track2 = await Track.query.create(title="Heart don't stand a chance", position=2)
    track3 = await Track.query.create(title="The Waters", position=3)

    album = await Album.query.create(name="Malibu", tracks=[track1, track2, track3])
    assert isinstance(album.tracks, ManyRelation)
    assert hasattr(track1, "track_albumtrack")
    retrieved_album = await track1.track_albumtrack.get()
    assert retrieved_album.pk == album.pk
    assert retrieved_album.embedded.track.pk == track1.pk
    await retrieved_album.load()
    assert retrieved_album == album

    embedded_track = await album.tracks.filter(embedded__track__title=track1.title).get()
    assert embedded_track.pk == track1.pk
    assert embedded_track.embedded.album.pk == album.pk

    await album.tracks.add(track3)


async def test_add_many_to_many_unique_conflict():
    track1 = await Track.query.create(title="The Bird", position=1)
    track2 = await Track.query.create(title="Heart don't stand a chance", position=2)
    track3 = await Track.query.create(title="The Waters", position=3)

    album = await Album.query.create(name="Malibu", tracks=[track1, track2, track3])
    album2 = await Album.query.create(name="Karamba")

    assert await album2.tracks.add(track3) is None
    retrieved_album = await track3.track_albumtrack.get()
    assert retrieved_album.pk == album.pk

    await track3.track_albumtrack.remove()
    assert await album2.tracks.add(track3)

    retrieved_album = await track3.track_albumtrack.get()
    assert retrieved_album.pk == album2.pk
