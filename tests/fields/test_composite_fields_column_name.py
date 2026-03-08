from typing import Any

import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class MyModel(saffier.StrictModel):
    ümbedded: dict[str, Any] = saffier.CompositeField(
        inner_fields=[
            ("first_name", saffier.CharField(max_length=255, exclude=True)),
            ("last_name", saffier.CharField(max_length=255, exclude=True, column_name="lname")),
        ],
        prefix_embedded="ämbedded_",
        prefix_column_name="embedded_",
        exclude=False,
    )

    class Meta:
        registry = models
        tablename = "composite_column_name_models"


@pytest.fixture(autouse=True)
async def create_test_database():
    async with database:
        await models.create_all()
        async with models:
            yield
        if not database.drop:
            await models.drop_all()


async def test_check():
    assert "ümbedded" in MyModel.meta.fields
    assert "ämbedded_first_name" in MyModel.meta.fields
    assert "ämbedded_last_name" in MyModel.meta.fields
    assert MyModel.table.columns["ämbedded_first_name"].name == "embedded_first_name"
    assert MyModel.table.columns["ämbedded_last_name"].name == "embedded_lname"


async def test_assign():
    obj = await MyModel.query.create(ümbedded={"first_name": "edgy", "last_name": "edgytoo"})
    assert obj.ümbedded["first_name"] == "edgy"
    assert obj.ümbedded["last_name"] == "edgytoo"
    obj.ümbedded = {"first_name": "Santa", "last_name": "Clause"}
    assert obj.ümbedded["first_name"] == "Santa"
    assert obj.ümbedded["last_name"] == "Clause"
    await obj.save()


async def test_save():
    obj = await MyModel.query.create(ümbedded={"first_name": "edgy", "last_name": "edgytoo"})
    assert obj.ümbedded["first_name"] == "edgy"
    assert obj.ümbedded["last_name"] == "edgytoo"
    await obj.save(values={"ümbedded": {"first_name": "Santa", "last_name": "Clause"}})
    assert obj.ümbedded["first_name"] == "Santa"
    assert obj.ümbedded["last_name"] == "Clause"
