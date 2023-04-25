import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class Album(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Track(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    album = saffier.ForeignKey("Album", on_delete=saffier.CASCADE, related_name="tracks")
    title = saffier.CharField(max_length=100)
    position = saffier.IntegerField()

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


# class Member(saffier.Model):
#     id = saffier.IntegerField(primary_key=True)
#     team = saffier.ForeignKey(Team, on_delete=saffier.SET_NULL, null=True)
#     email = saffier.CharField(max_length=100)

#     class Meta:
#         registry = models


# class Profile(saffier.Model):
#     id = saffier.IntegerField(primary_key=True)
#     website = saffier.CharField(max_length=100)

#     class Meta:
#         registry = models


# class Person(saffier.Model):
#     id = saffier.IntegerField(primary_key=True)
#     email = saffier.CharField(max_length=100)
#     profile = saffier.OneToOneField(Profile, on_delete=saffier.CASCADE)

#     class Meta:
#         registry = models


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


async def test_model_crud():
    album = await Album.query.create(name="Malibu")
    await Track.query.create(album=album, title="The Bird", position=1)
    await Track.query.create(album=album, title="Heart don't stand a chance", position=2)
    await Track.query.create(album=album, title="The Waters", position=3)

    track = await Track.query.get(title="The Bird")

    assert track.album.pk == album.pk
    await track.album.load()
    assert track.album.name == "Malibu"


async def test_related_field():
    album = await Album.query.create(name="Malibu")
    album2 = await Album.query.create(name="Queen")

    track1 = await Track.query.create(album=album, title="The Bird", position=1)
    track2 = await Track.query.create(album=album, title="Heart don't stand a chance", position=2)
    track3 = await Track.query.create(album=album2, title="The Waters", position=3)

    tracks_album_one = await album.tracks.all()
    tracks_and_titles = [track.title for track in tracks_album_one]

    assert len(tracks_album_one) == 2
    assert track1.title in tracks_and_titles
    assert track2.title in tracks_and_titles
    assert track3.title not in tracks_and_titles

    tracks_album_two = await album2.tracks.all()
    tracks_and_titles = [track.title for track in tracks_album_two]

    assert len(tracks_album_two) == 1
    assert track3.title in tracks_and_titles


async def test_related_field_with_filter():
    album = await Album.query.create(name="Malibu")
    album2 = await Album.query.create(name="Queen")

    track = await Track.query.create(album=album, title="The Bird", position=1)
    await Track.query.create(album=album, title="Heart don't stand a chance", position=2)
    await Track.query.create(album=album2, title="The Waters", position=3)

    tracks_album_one = await album.tracks.filter(title=track.title)

    assert len(tracks_album_one) == 1
    assert tracks_album_one[0].pk == track.pk


async def test_related_field_with_filter_return_empty():
    album = await Album.query.create(name="Malibu")
    album2 = await Album.query.create(name="Queen")

    await Track.query.create(album=album, title="The Bird", position=1)
    await Track.query.create(album=album, title="Heart don't stand a chance", position=2)
    track = await Track.query.create(album=album2, title="The Waters", position=3)

    tracks_album_one = await album.tracks.filter(title=track.title)

    assert len(tracks_album_one) == 0


async def test_related_name_empty():
    acme = await Organisation.query.create(ident="ACME Ltd")
    await Team.query.create(org=acme, name="Red Team")
    await Team.query.create(org=acme, name="Blue Team")

    teams = await acme.teams_set.all()

    assert len(teams) == 2


async def test_related_name_empty_return_one_result():
    acme = await Organisation.query.create(ident="ACME Ltd")
    red_team = await Team.query.create(org=acme, name="Red Team")
    await Team.query.create(org=acme, name="Blue Team")

    teams = await acme.teams_set.filter(name=red_team.name)

    assert len(teams) == 1
    assert teams[0].pk == red_team.pk


async def test_related_name_empty_return_one_result_with_limit():
    acme = await Organisation.query.create(ident="ACME Ltd")
    red_team = await Team.query.create(org=acme, name="Red Team")
    await Team.query.create(org=acme, name="Blue Team")

    teams = await acme.teams_set.filter(name=red_team.name).limit(1)

    assert len(teams) == 1
    assert teams[0].pk == red_team.pk


async def test_related_name_empty_return_one_result_with_limits():
    acme = await Organisation.query.create(ident="ACME Ltd")
    await Team.query.create(org=acme, name="Red Team")
    await Team.query.create(org=acme, name="Blue Team")

    teams = await acme.teams_set.filter().limit(1)

    assert len(teams) == 1

    teams = await acme.teams_set.filter().limit(2)

    assert len(teams) == 2
