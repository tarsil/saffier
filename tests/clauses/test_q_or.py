import contextlib
from typing import ClassVar

import pytest

import saffier
from saffier.core.db import fields
from saffier.core.db.models.managers import Manager
from saffier.core.db.querysets import Q, QuerySet
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class UniqueWorkspaceQuerySet(QuerySet):
    def filter(self, *clauses, **lookups):  # type: ignore[override]
        return super().filter(*clauses, **lookups).distinct()


class WorkspaceManager(Manager):
    queryset_class = UniqueWorkspaceQuerySet


class Group(saffier.Model):
    id: int = fields.IntegerField(autoincrement=True, primary_key=True)
    name: str = fields.CharField(max_length=128)

    class Meta:
        registry = models
        tablename = "qor_groups"


class Collection(saffier.Model):
    id: int = fields.IntegerField(autoincrement=True, primary_key=True)
    name: str = fields.CharField(max_length=128)
    groups: list[Group] = fields.ManyToManyField(  # type: ignore[assignment]
        "Group",
        through_tablename=saffier.NEW_M2M_NAMING,
        related_name="collections",
    )

    class Meta:
        registry = models
        tablename = "qor_collections"


class Workspace(saffier.Model):
    id: int = fields.IntegerField(autoincrement=True, primary_key=True)
    name: str = fields.CharField(max_length=128)
    collection: Collection = fields.ForeignKey(  # type: ignore[assignment]
        "Collection",
        related_name="workspaces",
        on_delete=saffier.CASCADE,
    )

    objects: ClassVar[WorkspaceManager] = WorkspaceManager()  # type: ignore[assignment]

    class Meta:
        registry = models
        tablename = "qor_workspaces"


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    async with database:
        with contextlib.suppress(Exception):
            await models.drop_all()
        await models.create_all()
        yield


@pytest.fixture(autouse=True, scope="function")
async def rollback_transactions():
    with database.force_rollback():
        async with database:
            yield


async def test_custom_manager_uses_custom_queryset_class_for_q_or():
    qs = Workspace.objects.filter(Q(id=1) | Q(id=2))
    assert isinstance(qs, QuerySet)


async def test_q_or_with_custom_queryset_returns_single_workspace():
    g1 = await Group.query.create(name="group-a")
    g2 = await Group.query.create(name="group-b")

    collection = await Collection.query.create(name="col-1")
    await collection.groups.add(g1)
    await collection.groups.add(g2)

    workspace = await Workspace.objects.create(name="ws-1", collection=collection)

    qs = Workspace.objects.filter(
        Q(collection__groups__name="group-a") | Q(collection__groups__name="group-b")
    )
    results = await qs

    assert len(results) == 1
    assert results[0].id == workspace.id
    assert results[0].name == "ws-1"


async def test_q_or_does_not_duplicate_with_and_condition():
    g1 = await Group.query.create(name="ga")
    g2 = await Group.query.create(name="gb")

    collection = await Collection.query.create(name="c")
    await collection.groups.add(g1)
    await collection.groups.add(g2)

    workspace = await Workspace.objects.create(name="w", collection=collection)

    qs = Workspace.objects.filter(
        (Q(collection__groups__name="ga") | Q(collection__groups__name="gb")) & Q(name="w")
    )
    results = await qs

    assert len(results) == 1
    assert results[0].id == workspace.id


async def test_q_or_does_not_affect_exists_uniqueness_checks():
    group = await Group.query.create(name="support")

    collection = await Collection.query.create(name="main")
    await collection.groups.add(group)

    await Workspace.objects.create(name="exist", collection=collection)

    assert await Workspace.objects.filter(name="exist", collection=collection).exists()
    assert not await Workspace.objects.filter(name="not-there", collection=collection).exists()


async def test_select_related_does_not_duplicate_rows():
    g1 = await Group.query.create(name="g1")
    g2 = await Group.query.create(name="g2")

    collection = await Collection.query.create(name="cc")
    await collection.groups.add(g1)
    await collection.groups.add(g2)

    workspace = await Workspace.objects.create(name="ws", collection=collection)

    results = await Workspace.objects.select_related("collection").filter(
        Q(collection__groups__name="g1") | Q(collection__groups__name="g2")
    )

    assert len(results) == 1
    assert results[0].id == workspace.id
    assert results[0].collection.id == collection.id
