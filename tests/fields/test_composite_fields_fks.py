import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class MyModel1(saffier.StrictModel):
    embedded = saffier.CompositeField(
        inner_fields=[
            ("embedder", saffier.ForeignKey("MyModel1", null=True)),
        ],
    )

    class Meta:
        registry = models
        tablename = "composite_fk_model1"


class MyModelEmbed(saffier.StrictModel):
    embedder = saffier.ForeignKey("MyModel2", null=True)

    class Meta:
        abstract = True


class MyModel2(saffier.StrictModel):
    embedded = MyModelEmbed

    class Meta:
        registry = models
        tablename = "composite_fk_model2"


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    async with database:
        await models.create_all()
        yield


@pytest.fixture(autouse=True)
async def rollback_transactions():
    async with models:
        yield


@pytest.mark.parametrize("model_class", [MyModel1, MyModel2])
async def test_model_create_update_delete(model_class):
    instance = await model_class.query.create()
    assert instance.id
    instance.embedded = {"embedder": instance}
    await instance.save()
    instance.model_dump()
    await instance.delete()
