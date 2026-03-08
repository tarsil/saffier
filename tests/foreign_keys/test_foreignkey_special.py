import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class Album(saffier.Model):
    album_id = saffier.IntegerField(primary_key=True, autoincrement=True, column_name="id")
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        tablename = "albums_special"


class Track(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    album = saffier.ForeignKey("Album", on_delete=saffier.CASCADE, null=True, column_name="album")
    title = saffier.CharField(max_length=100)
    position = saffier.IntegerField()

    class Meta:
        registry = models
        tablename = "tracks_special"


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


async def test_reverse_relation_add_remove_with_custom_column_names():
    track1 = await Track.query.create(title="The Bird", position=1)
    track2 = await Track.query.create(title="Heart don't stand a chance", position=2)
    await Track.query.create(title="The Waters", position=3)

    album = await Album.query.create(name="Malibu")
    await album.tracks_set.add(track1)
    await album.tracks_set.add(track2)

    tracks = await album.tracks_set.all()
    assert len(tracks) == 2

    await album.tracks_set.remove(track2)
    tracks = await album.tracks_set.all()
    assert len(tracks) == 1


async def test_create_with_reverse_relation_payload_and_select_related_filtering():
    album = await Album.query.create(name="Fantasies")
    await Track.query.create(album=album, title="Help I'm Alive", position=1)
    await Track.query.create(album=album, title="Sick Muse", position=2)
    await Track.query.create(album=album, title="Satellite Mind", position=3)

    track = await Track.query.select_related("album").get(title="Help I'm Alive")
    assert track.album.name == "Fantasies"

    tracks = await Track.query.filter(album__name__icontains="fan").select_related("album").all()
    assert len(tracks) == 3
    assert all(item.album.name == "Fantasies" for item in tracks)


async def test_queryset_update_and_delete_with_custom_column_name_fk():
    malibu = await Album.query.create(name="Malibu")
    wall = await Album.query.create(name="The Wall")
    await Track.query.create(album=malibu, title="The Bird", position=1)

    await Track.query.filter(album=malibu).update(album=wall)
    assert await Track.query.filter(album=malibu).count() == 0
    assert await Track.query.filter(album=wall).count() == 1

    await Track.query.filter(album=wall).delete()
    assert await Track.query.count() == 0
