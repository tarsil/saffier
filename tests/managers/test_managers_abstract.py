import pytest
from tests.settings import DATABASE_URL

import saffier
from saffier import Manager
from saffier.testclient import DatabaseTestClient as Database
from saffier.db.queryset import QuerySet

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class ObjectsManager(Manager):
    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset().filter(is_active=True)
        return queryset


class LanguageManager(Manager):
    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset().filter(language="EN")
        return queryset


class BaseModel(saffier.Model):
    query = ObjectsManager()

    class Meta:
        abstract = True
        registry = models


class HubUser(BaseModel):
    name = saffier.CharField(max_length=100)
    language = saffier.CharField(max_length=200, null=True)

    languages = LanguageManager()

    class Meta:
        registry = models


class HubProduct(BaseModel):
    name = saffier.CharField(max_length=100)
    rating = saffier.IntegerField(minimum=1, maximum=5)
    in_stock = saffier.BooleanField(default=False)
    is_active = saffier.BooleanField(default=False)


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


@pytest.mark.parametrize("manager,total", [("query", 4), ("languages", 2)])
async def test_inherited_abstract_base_model_managers(manager, total):
    await HubUser.query.create(name="test", language="EN")
    await HubUser.query.create(name="test2", language="EN")
    await HubUser.query.create(name="test3", language="PT")
    await HubUser.query.create(name="test4", language="PT")

    users = await getattr(HubUser, manager).all()
    assert len(users) == total
