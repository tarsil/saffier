import contextlib
from contextlib import asynccontextmanager

import pytest
import sqlalchemy

import saffier
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL, full_isolation=False)
models = saffier.Registry(database=database)


class User(saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=200, null=True)

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="function")
async def create_test_database():
    async with database:
        await models.create_all()
        yield
        if not database.drop:
            await models.drop_all()


@asynccontextmanager
async def txn():
    async with database.transaction():
        yield


async def test_select_for_update_basic_update():
    user = await User.query.create(name="John", language="PT")

    async with txn():
        locked = await User.query.filter(id=user.id).select_for_update().get()
        locked.language = "EN"
        await locked.save()

    fresh = await User.query.get(id=user.id)
    assert fresh.language == "EN"


async def test_select_for_update_nowait_lock_conflict():
    user = await User.query.create(name="Jane", language="EN")

    other = DatabaseTestClient(DATABASE_URL, full_isolation=False)
    await other.connect()

    def on(db, qs):
        queryset = qs.all()
        queryset.database = db
        return queryset

    async with txn():
        await User.query.filter(id=user.id).select_for_update().get()

        async def try_lock_nowait_on_other_conn():
            async with other.transaction():
                return await on(
                    other, User.query.filter(id=user.id).select_for_update(nowait=True)
                ).get()

        with pytest.raises((sqlalchemy.exc.OperationalError, sqlalchemy.exc.DBAPIError)):
            await try_lock_nowait_on_other_conn()

    with contextlib.suppress(Exception):
        await other.disconnect()


async def test_select_for_update_skip_locked_excludes_locked_rows():
    user = await User.query.create(name="A", language="X")
    await User.query.create(name="B", language="Y")

    def on(db):
        queryset = User.query.filter()
        queryset.database = db
        return queryset

    other = DatabaseTestClient(DATABASE_URL, full_isolation=False)
    await other.connect()

    try:
        async with txn():
            await User.query.filter(id=user.id).select_for_update().get()

            async with other.transaction():
                remaining = await on(other).order_by("id").select_for_update(skip_locked=True)
                ids = [model.id for model in remaining]
                assert user.id not in ids
                assert ids == [2]
    finally:
        await other.disconnect()


async def test_select_for_update_compiles_for_update_clause_present():
    queryset = User.query.select_for_update()

    sql = queryset.sql.upper()

    assert "FOR UPDATE" in sql


async def test_select_for_update_is_noop_outside_txn():
    user = await User.query.create(name="Solo", language="SQ")
    rows = await User.query.filter(id=user.id).select_for_update()

    assert len(rows) == 1
    assert rows[0].id == user.id


async def test_select_for_update_of_and_shared_variants_compile_and_run():
    await User.query.create(name="PG", language="SH")

    queryset = User.query.select_for_update(read=True, of=[User])
    sql = queryset.sql.upper()

    assert "FOR SHARE" in sql or "FOR UPDATE" in sql
    assert " OF " in sql

    async with txn():
        rows = await queryset.limit(1)
        assert len(rows) >= 0


async def test_select_for_update_preserved_through_all_clone_and_clear_cache():
    user = await User.query.create(name="John", language="PT")

    queryset = User.query.filter(id=user.id).select_for_update()
    queryset_clone = queryset.all()
    assert "FOR UPDATE" in queryset_clone.sql.upper()

    queryset_same = queryset.all(True)
    assert "FOR UPDATE" in queryset_same.sql.upper()


async def test_select_for_update_filter_before_vs_after_equivalent_results():
    user = await User.query.create(name="A", language="X")

    queryset = User.query.filter(id=user.id).select_for_update()
    queryset2 = User.query.select_for_update().filter(id=user.id)

    async with txn():
        result = await queryset.limit(1)
        result2 = await queryset2.limit(1)

    assert [model.id for model in result] == [user.id]
    assert [model.id for model in result2] == [user.id]


async def test_select_for_update_multiple_filters_chain():
    user = await User.query.create(name="B", language="Y")

    async with txn():
        rows = await User.query.filter(language="Y").filter(id=user.id).select_for_update().limit(1)
    assert [model.id for model in rows] == [user.id]


async def test_select_for_update_skip_locked_with_filter_subset_excludes_locked_row():
    user = await User.query.create(name="A", language="X")
    user2 = await User.query.create(name="B", language="Y")

    def bind(qs, db):
        queryset = qs.all()
        queryset.database = db
        return queryset

    other = DatabaseTestClient(DATABASE_URL, full_isolation=False)
    await other.connect()

    try:
        async with txn():
            await User.query.filter(id=user.id).select_for_update().get()

            async with other.transaction():
                queryset = (
                    User.query.filter(id__in=[user.id, user2.id])
                    .order_by("id")
                    .select_for_update(skip_locked=True)
                )
                rows = await bind(queryset, other)
                ids = [model.id for model in rows]
                assert user.id not in ids
                assert ids == [user2.id]
    finally:
        with contextlib.suppress(Exception):
            await other.disconnect()


async def test_select_for_update_nowait_with_filter_raises_on_locked_row():
    user = await User.query.create(name="C", language="Z")

    def bind(qs, db):
        queryset = qs.all()
        queryset.database = db
        return queryset

    other = DatabaseTestClient(DATABASE_URL, full_isolation=False)
    await other.connect()

    try:
        async with txn():
            await User.query.filter(id=user.id).select_for_update().get()

            async with other.transaction():
                queryset = User.query.filter(id=user.id).select_for_update(nowait=True)
                with pytest.raises((sqlalchemy.exc.OperationalError, sqlalchemy.exc.DBAPIError)):
                    await bind(queryset, other).get()
    finally:
        with contextlib.suppress(Exception):
            await other.disconnect()
