import pytest

import saffier
from saffier.core.db.querysets import Prefetch
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


class Studio(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    album = saffier.ForeignKey("Album", related_name="studios")
    name = saffier.CharField(max_length=255)

    class Meta:
        registry = models


class Company(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    studio = saffier.ForeignKey(Studio, related_name="companies")

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


async def test_prefetch_related():
    album = await Album.query.create(name="Malibu")
    await Track.query.create(album=album, title="The Bird", position=1)
    await Track.query.create(album=album, title="Heart don't stand a chance", position=2)
    await Track.query.create(album=album, title="The Waters", position=3)

    album2 = await Album.query.create(name="West")
    await Track.query.create(album=album2, title="The Bird", position=1)

    stud = await Studio.query.create(album=album, name="Valentim")

    studio = await Studio.query.prefetch_related(
        Prefetch(related_name="studios__tracks", to_attr="tracks"),
    ).get(pk=stud.pk)

    assert len(studio.tracks) == 3

    stud = await Studio.query.create(album=album2, name="New")

    studio = await Studio.query.prefetch_related(
        Prefetch(related_name="studios__tracks", to_attr="tracks"),
    ).get(pk=stud.pk)

    assert len(studio.tracks) == 1


async def test_prefetch_related_nested():
    album = await Album.query.create(name="Malibu")
    await Track.query.create(album=album, title="The Bird", position=1)

    album2 = await Album.query.create(name="West")
    await Track.query.create(album=album2, title="The Bird", position=1)

    stud = await Studio.query.create(album=album, name="Valentim")

    await Company.query.create(studio=stud)

    company = await Company.query.prefetch_related(
        Prefetch(related_name="companies__studios__tracks", to_attr="tracks")
    )

    assert len(company[0].tracks) == 1

    company = await Company.query.prefetch_related(
        Prefetch(related_name="companies__studios__tracks", to_attr="tracks")
    ).get(studio=stud)

    assert len(company.tracks) == 1


async def test_prefetch_related_nested_with_queryset():
    album = await Album.query.create(name="Malibu")
    await Track.query.create(album=album, title="The Bird", position=1)

    album2 = await Album.query.create(name="West")
    await Track.query.create(album=album2, title="The Bird", position=1)

    stud = await Studio.query.create(album=album, name="Valentim")

    await Company.query.create(studio=stud)

    company = await Company.query.prefetch_related(
        Prefetch(
            related_name="companies__studios__tracks",
            to_attr="tracks",
            queryset=Track.query.filter(title__icontains="bird"),
        )
    )

    assert len(company[0].tracks) == 1
