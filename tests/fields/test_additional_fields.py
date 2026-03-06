import datetime
import enum

import pytest

import saffier
from saffier.exceptions import ValidationError
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class Status(enum.Enum):
    PENDING = "pending"
    DONE = "done"


class Document(saffier.Model):
    name = saffier.CharField(max_length=100)
    payload = saffier.BinaryField(max_length=8, null=True)
    elapsed = saffier.DurationField(null=True)
    small_score = saffier.SmallIntegerField(null=True)
    status = saffier.CharChoiceField(choices=Status, max_length=20, null=True)

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connection():
    with database.force_rollback():
        async with database:
            yield


async def test_additional_fields_roundtrip():
    doc = await Document.query.create(
        name="doc",
        payload=b"abc",
        elapsed=datetime.timedelta(seconds=12),
        small_score=7,
        status="pending",
    )
    fetched = await Document.query.get(pk=doc.pk)

    assert fetched.payload == b"abc"
    assert fetched.elapsed == datetime.timedelta(seconds=12)
    assert fetched.small_score == 7
    assert fetched.status == "pending"


async def test_binary_field_max_length_validation():
    with pytest.raises(ValidationError):
        await Document.query.create(name="invalid", payload=b"too-long-value")
