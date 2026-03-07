import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class Album(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)
    tracks = saffier.ManyToMany("Track", related_name=False)

    class Meta:
        registry = models


class Track(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    title = saffier.CharField(max_length=100)
    position = saffier.IntegerField()

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


async def test_no_related_name_reverse_relation_is_created() -> None:
    assert Album.fields["tracks"].related_name is False
    assert not any(field_name.endswith("_set") for field_name in Track.meta.fields)
    assert not any(name.endswith("_set") for name in Track.meta.related_fields)


async def test_many_to_many_without_related_name_still_manages_links() -> None:
    album = await Album.query.create(name="Malibu")
    second_album = await Album.query.create(name="Santa Monica")

    track_one = await Track.query.create(title="The Bird", position=1)
    track_two = await Track.query.create(title="Heart don't stand a chance", position=2)
    track_three = await Track.query.create(title="The Waters", position=3)

    await album.tracks.add(track_one)
    await album.tracks.add(track_two)
    await second_album.tracks.add(track_three)

    album_tracks = await album.tracks.all()
    assert len(album_tracks) == 2
    assert {track.pk for track in album_tracks} == {track_one.pk, track_two.pk}
