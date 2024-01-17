import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_ALTERNATIVE_URL, DATABASE_URL

database = Database(url=DATABASE_URL)
another_db = Database(url=DATABASE_ALTERNATIVE_URL)

registry = saffier.Registry(database=database, extra={"alternative": another_db})
pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    try:
        await registry.create_all()
        yield
        await registry.drop_all()
    except Exception:
        pytest.skip("No database available")


@pytest.fixture(autouse=True)
async def rollback_connections():
    with database.force_rollback():
        async with database:
            yield

    with another_db.force_rollback():
        async with another_db:
            yield


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=255, null=True)

    class Meta:
        registry = registry


def test_has_multiple_connections():
    assert "alternative" in User.meta.registry.extra
