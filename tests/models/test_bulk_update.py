import datetime
from enum import Enum

import pytest

import saffier
from saffier.core.db import fields
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


def time():
    return datetime.datetime.now().time()


class StatusEnum(Enum):
    DRAFT = "Draft"
    RELEASED = "Released"


class BaseModel(saffier.Model):
    id = fields.IntegerField(primary_key=True)

    class Meta:
        registry = models


class Product(BaseModel):
    uuid = fields.UUIDField(null=True)
    created = fields.DateTimeField(default=datetime.datetime.now)
    created_day = fields.DateField(default=datetime.date.today)
    created_time = fields.TimeField(default=time)
    created_date = fields.DateField(auto_now_add=True)
    created_datetime = fields.DateTimeField(auto_now_add=True)
    updated_datetime = fields.DateTimeField(auto_now=True)
    updated_date = fields.DateField(auto_now=True)
    data = fields.JSONField(default={})
    description = fields.CharField(blank=True, max_length=255)
    huge_number = fields.BigIntegerField(default=0)
    price = fields.DecimalField(max_digits=5, decimal_places=2, null=True)
    status = fields.ChoiceField(StatusEnum, default=StatusEnum.DRAFT)
    value = fields.FloatField(null=True)


class Album(BaseModel):
    name = saffier.CharField(max_length=100)


class Track(BaseModel):
    album = saffier.ForeignKey("Album", on_delete=saffier.CASCADE)
    title = saffier.CharField(max_length=100)
    position = saffier.IntegerField()


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_transactions():
    with database.force_rollback():
        async with database:
            yield


async def test_bulk_update():
    await Product.query.bulk_create(
        [
            {"data": {"foo": 123}, "value": 123.456, "status": StatusEnum.RELEASED},
            {"data": {"foo": 456}, "value": 456.789, "status": StatusEnum.DRAFT},
        ]
    )
    products = await Product.query.all()
    assert len(products) == 2
    assert products[0].data == {"foo": 123}
    assert products[0].value == 123.456
    assert products[0].status == StatusEnum.RELEASED
    assert products[1].data == {"foo": 456}
    assert products[1].value == 456.789
    assert products[1].status == StatusEnum.DRAFT

    today_date = datetime.date.today() + datetime.timedelta(days=3)

    products = await Product.query.all()
    products[0].created_day = today_date
    products[1].created_day = today_date
    products[0].status = StatusEnum.DRAFT
    products[1].status = StatusEnum.RELEASED
    products[0].data = {"foo": "test"}
    products[1].data = {"foo": "test2"}
    products[0].value = 1
    products[1].value = 2

    await Product.query.bulk_update(products, fields=["created_day", "status", "data", "value"])

    products = await Product.query.all()

    assert products[0].created_day == today_date
    assert products[1].created_day == today_date
    assert products[0].status == StatusEnum.DRAFT
    assert products[1].status == StatusEnum.RELEASED
    assert products[0].data == {"foo": "test"}
    assert products[1].data == {"foo": "test2"}
    assert products[0].value == 1
    assert products[1].value == 2


async def test_bulk_update_with_relation():
    album = await Album.query.create(name="foo")
    album2 = await Album.query.create(name="fighters")

    await Track.query.bulk_create(
        [
            {"name": "foo", "album": album, "position": 1, "title": "foo"},
            {"name": "bar", "album": album, "position": 2, "title": "fighters"},
        ]
    )
    tracks = await Track.query.all()
    for track in tracks:
        track.album = album2

    await Track.query.bulk_update(tracks, fields=["album"])
    tracks = await Track.query.all()
    assert tracks[0].album.pk == album2.pk
    assert tracks[1].album.pk == album2.pk
