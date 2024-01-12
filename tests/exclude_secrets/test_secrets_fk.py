import datetime

import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class User(saffier.Model):
    first_name = saffier.CharField(max_length=255)
    last_name = saffier.CharField(max_length=255, secret=True)
    email = saffier.EmailField(max_length=255)

    class Meta:
        registry = models


class Gratitude(saffier.Model):
    owner = saffier.ForeignKey(User, related_name="gratitude")
    title = saffier.CharField(max_length=100)
    description = saffier.TextField()
    color = saffier.CharField(max_length=10, null=True)
    is_visible = saffier.BooleanField(default=False)
    created_at: datetime.datetime = saffier.DateTimeField(auto_now=True)
    updated_at: datetime.datetime = saffier.DateTimeField(auto_now_add=True)

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


async def test_exclude_secrets():
    user = await User.query.create(
        first_name="Edgy",
        last_name="ORM",
        email="saffier@saffier.dev",
    )

    gratitude = await Gratitude.query.create(
        owner=user, title="test", description="A desc", color="green"
    )

    results = (
        await Gratitude.query.or_(
            owner__first_name__icontains="e",
            owner__last_name__icontains="o",
            owner__email__icontains="saffier",
            title__icontains="te",
            description__icontains="desc",
            color__icontains="green",
        )
        .exclude_secrets()
        .all()
    )
    result = results[0]

    assert len(results) == 1
    assert result.pk == gratitude.pk

    assert result.owner.model_dump() == {
        "id": 1,
        "first_name": "Edgy",
        "email": "saffier@saffier.dev",
    }
