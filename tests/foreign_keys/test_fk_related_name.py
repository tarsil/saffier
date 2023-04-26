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


class Member(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    team = saffier.ForeignKey(Team, on_delete=saffier.SET_NULL, null=True, related_name="members")
    second_team = saffier.ForeignKey(
        Team, on_delete=saffier.SET_NULL, null=True, related_name="team_members"
    )
    email = saffier.CharField(max_length=100)
    name = saffier.CharField(max_length=255, null=True)

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


async def test_related_name_nested_query():
    acme = await Organisation.query.create(ident="ACME Ltd")
    red_team = await Team.query.create(org=acme, name="Red Team")
    blue_team = await Team.query.create(org=acme, name="Blue Team")

    # members
    charlie = await Member.query.create(team=red_team, email="charlie@redteam.com")
    brown = await Member.query.create(team=red_team, email="brown@redteam.com")
    monica = await Member.query.create(team=blue_team, email="monica@blueteam.com")
    snoopy = await Member.query.create(team=blue_team, email="snoopy@blueteam.com")

    teams = await acme.teams_set.all()

    assert len(teams) == 2

    # red team
    teams = await acme.teams_set.filter(members=red_team)

    assert len(teams) == 1
    assert teams[0].pk == red_team.pk

    # blue team
    teams = await acme.teams_set.filter(members=blue_team).get()

    assert teams.pk == blue_team.pk

    # nested_field by team
    breakpoint()
    teams = await acme.teams_set.filter(members__email__iexact=charlie.email)

    assert len(teams) == 1
    assert teams[0].pk == red_team.pk

    teams = await acme.teams_set.filter(members__email=brown.email)

    assert len(teams) == 1
    assert teams[0].pk == red_team.pk

    teams = await acme.teams_set.filter(members__email=monica.email)

    assert len(teams) == 1
    assert teams[0].pk == blue_team.pk

    teams = await acme.teams_set.filter(members__email=snoopy.email)

    assert len(teams) == 1
    assert teams[0].pk == blue_team.pk


async def test_related_name_nested_query_multiple_foreign_keys():
    acme = await Organisation.query.create(ident="ACME Ltd")
    red_team = await Team.query.create(org=acme, name="Red Team")
    blue_team = await Team.query.create(org=acme, name="Blue Team")
    green_team = await Team.query.create(org=acme, name="Green Team")

    # members
    charlie = await Member.query.create(
        team=red_team, email="charlie@redteam.com", team2=green_team, name="Charlie"
    )
    brown = await Member.query.create(team=red_team, email="brown@redteam.com", name="Brown")
    monica = await Member.query.create(
        team=blue_team, email="monica@blueteam.com", team2=green_team, name="Monica"
    )
    snoopy = await Member.query.create(team=blue_team, email="snoopy@blueteam.com", name="Snoopy")

    teams = await acme.teams_set.all()

    assert len(teams) == 3

    # red team
    teams = await acme.teams_set.filter(members=red_team)

    assert len(teams) == 1
    assert teams[0].pk == red_team.pk

    # blue team
    teams = await acme.teams_set.filter(members=blue_team)

    assert len(teams) == 1
    assert teams[0].pk == blue_team.pk

    # blue team
    teams = await acme.teams_set.filter(members=green_team)

    assert len(teams) == 1
    assert teams[0].pk == green_team.pk

    # nested_field by team
    teams = await acme.teams_set.filter(members__email=charlie.email)

    assert len(teams) == 1
    assert teams[0].pk == red_team.pk

    teams = await acme.teams_set.filter(members__email=brown.email)

    assert len(teams) == 1
    assert teams[0].pk == red_team.pk

    teams = await acme.teams_set.filter(members__email=monica.email)

    assert len(teams) == 1
    assert teams[0].pk == blue_team.pk

    teams = await acme.teams_set.filter(members__email=snoopy.email)

    assert len(teams) == 1
    assert teams[0].pk == blue_team.pk

    # nested_field by team_members FK
    teams = await acme.teams_set.filter(team_members__email=brown.email)

    assert len(teams) == 0

    teams = await acme.teams_set.filter(team_members__email=snoopy.email)

    assert len(teams) == 0

    teams = await acme.teams_set.filter(team_members__email=charlie.email)

    assert len(teams) == 1
    assert teams[0].pk == green_team.pk

    teams = await acme.teams_set.filter(team_members__email=monica.email)

    assert len(teams) == 1
    assert teams[0].pk == green_team.pk

    teams = await acme.teams_set.filter(team_members__name__icontains=monica.name)

    assert len(teams) == 1
    assert teams[0].pk == green_team.pk

    teams = await acme.teams_set.filter(team_members__name__icontains=snoopy.name)

    assert len(teams) == 0

    # Using distinct
    teams = await acme.teams_set.filter(team_members__id__in=[monica.pk, charlie.pk]).distinct(
        "name"
    )

    assert len(teams) == 1
    assert teams[0].pk == green_team.pk
