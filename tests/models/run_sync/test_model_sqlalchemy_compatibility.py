import uuid

import pytest
import sqlalchemy

import saffier
from saffier.exceptions import ImproperlyConfigured
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

database = DatabaseTestClient(DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class Owner(saffier.SQLAlchemyModelMixin, saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        table_prefix = "sa_sync"


class Workspace(saffier.SQLAlchemyModelMixin, saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)
    owner = saffier.ForeignKey(Owner, on_delete=saffier.CASCADE)

    class Meta:
        registry = models
        table_prefix = "sa_sync"


class Tag(saffier.SQLAlchemyModelMixin, saffier.StrictModel):
    id = saffier.UUIDField(primary_key=True, default=uuid.uuid4)
    label = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        table_prefix = "sa_sync"


class Article(saffier.SQLAlchemyModelMixin, saffier.StrictModel):
    id = saffier.CharField(max_length=30, primary_key=True, default="article-default")
    tags = saffier.ManyToMany(Tag, through_tablename=saffier.NEW_M2M_NAMING)

    class Meta:
        registry = models
        table_prefix = "sa_sync"


class PlainWorkspace(saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        table_prefix = "sa_sync"


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True, scope="function")
async def rollback_connections():
    with database.force_rollback():
        async with database:
            yield


async def test_sqlalchemy_core_class_attribute_select_where_and_order_by():
    owner = saffier.run_sync(Owner.query.create(name="ACME"))
    workspace1 = saffier.run_sync(Workspace.query.create(name="Alpha", owner=owner))
    workspace2 = saffier.run_sync(Workspace.query.create(name="Beta", owner=owner))

    statement = sqlalchemy.select(Workspace.id).where(Workspace.id == workspace1.id)
    row = saffier.run_sync(models.database.fetch_one(statement))
    assert row is not None
    assert row[0] == workspace1.id

    order_statement = sqlalchemy.select(Workspace.id).order_by(Workspace.id)
    ordered_rows = saffier.run_sync(models.database.fetch_all(order_statement))
    assert [row[0] for row in ordered_rows] == [workspace1.id, workspace2.id]


async def test_opted_out_models_keep_old_behavior():
    with pytest.raises(AttributeError):
        _ = PlainWorkspace.id


async def test_foreign_key_alias_is_supported_but_relationship_name_is_rejected():
    owner = saffier.run_sync(Owner.query.create(name="Owner"))
    workspace = saffier.run_sync(Workspace.query.create(name="Workspace", owner=owner))

    with pytest.raises(ImproperlyConfigured, match='Field "owner"'):
        _ = Workspace.owner

    statement = sqlalchemy.select(Workspace.owner_id).where(Workspace.owner_id == owner.id)
    row = saffier.run_sync(models.database.fetch_one(statement))
    assert row is not None
    assert row[0] == owner.id

    join_statement = (
        sqlalchemy.select(Workspace.id)
        .select_from(Workspace.table.join(Owner.table, Workspace.owner_id == Owner.id))
        .where(Owner.id == owner.id)
    )
    joined_row = saffier.run_sync(models.database.fetch_one(join_statement))
    assert joined_row is not None
    assert joined_row[0] == workspace.id


async def test_relationship_collections_are_not_scalar_columns():
    with pytest.raises(ImproperlyConfigured, match="many-to-many relation"):
        _ = Article.tags
