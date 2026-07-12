from __future__ import annotations

import pytest
import sqlalchemy

import saffier
from saffier.core.utils.db import with_force_fields_nullable
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(DATABASE_URL, full_isolation=False)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class NullableMigrationUser(saffier.Model):
    """Model used to prove migration-time nullable backfills.

    The ``nickname`` field is declared as required at the ORM layer but has a
    Python default. The test creates the database table while forcing that field
    nullable, inserts an existing-row shape with ``NULL`` directly through
    SQLAlchemy, and then asks the registry migration helper to apply the
    declared default.
    """

    id = saffier.IntegerField(primary_key=True)
    name = saffier.CharField(max_length=100)
    nickname = saffier.CharField(max_length=100, default="anonymous")

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="function")
async def create_test_database():
    """Create a nullable migration fixture table and drop it afterwards.

    The forced-nullable context is active only while metadata is built and DDL
    is emitted. That mirrors migration autogeneration, where Saffier temporarily
    relaxes generated columns without changing the model declaration itself.
    """
    with with_force_fields_nullable((("NullableMigrationUser", "nickname"),)):
        await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connections():
    """Run each test in an isolated database transaction.

    The registry helper uses normal ORM updates, while the setup inserts raw
    SQLAlchemy rows. Keeping both operations inside the test client's rollback
    wrapper ensures the fixture does not leak state into neighboring registry
    tests even when the database backend reuses connections.
    """
    with database.force_rollback():
        async with database:
            yield


async def test_registry_backfills_forced_nullable_field_defaults() -> None:
    """Verify forced-nullable migration defaults are applied through the ORM.

    A raw insert creates the exact state an online migration must repair: an
    existing row where a newly added required field is still ``NULL``. The
    registry helper receives the wildcard selector shape emitted by the CLI
    templates and must update the row using the model's declared default.
    """
    insert = sqlalchemy.insert(NullableMigrationUser.table).values(
        id=1,
        name="Ada",
        nickname=None,
    )
    async with database as db:
        await db.execute(insert)

    await models.apply_default_force_nullable_fields(
        force_fields_nullable=(("", "nickname"),),
        filter_db_name="",
    )

    user = await NullableMigrationUser.query.get(id=1)
    assert user.nickname == "anonymous"
