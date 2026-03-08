import pytest

import saffier
from saffier.exceptions import ValidationError
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class MyWebsite(saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=False)
    rev = saffier.IntegerField(increment_on_save=1, default=0)

    class Meta:
        registry = models


class MyRevision(saffier.StrictModel):
    id = saffier.BigIntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=50)
    rev = saffier.IntegerField(increment_on_save=1, primary_key=True, default=1)

    class Meta:
        registry = models


class MyCountdown(saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=50)
    rev = saffier.IntegerField(increment_on_save=-1, default=10, read_only=False)

    class Meta:
        registry = models


class MyCountdownNoDefault(saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=50)
    rev = saffier.IntegerField(increment_on_save=-1, read_only=False)

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


async def test_increment_on_save_for_regular_field():
    await MyWebsite.query.bulk_create([{"id": 1}, {"id": 2}])

    websites = await MyWebsite.query.order_by("id").all()
    assert [website.rev for website in websites] == [0, 0]

    await websites[0].save()
    assert websites[0].rev == 1

    await websites[1].load()
    assert websites[1].rev == 0


async def test_increment_on_save_creates_new_revision_for_primary_key():
    revision = await MyRevision.query.create(name="foo")
    assert revision.rev == 1

    await revision.save(values={"name": "bar"})
    assert revision.rev == 2

    revisions = await MyRevision.query.order_by("rev").all()
    assert len(revisions) == 2
    assert [(item.name, item.rev) for item in revisions] == [("foo", 1), ("bar", 2)]


async def test_force_insert_alias_is_supported():
    first = await MyRevision.query.create(name="foo")
    second = await first.real_save(force_insert=True, values={"name": "bar"})

    assert second.rev == 2
    assert await MyRevision.query.count() == 2


async def test_increment_on_save_allows_explicit_override():
    countdown = await MyCountdown.query.create(name="count")
    assert countdown.rev == 10

    await countdown.save()
    assert countdown.rev == 9

    await countdown.save(values={"rev": 100})
    assert countdown.rev == 100


async def test_increment_on_save_requires_explicit_value_without_default():
    with pytest.raises(ValidationError):
        await MyCountdownNoDefault.query.create(name="count")

    countdown = await MyCountdownNoDefault.query.create(name="count", rev=10)
    assert countdown.rev == 10

    await countdown.save()
    assert countdown.rev == 9
