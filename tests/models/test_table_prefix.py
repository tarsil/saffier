import pytest

import saffier
from saffier.core.db import fields
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class Product(saffier.StrictModel):
    id = fields.IntegerField(primary_key=True, autoincrement=True)
    uuid = fields.UUIDField(null=True)

    class Meta:
        table_prefix = "test"
        registry = models


class InheritProduct(Product):
    name = fields.CharField(null=True, max_length=255)

    class Meta:
        registry = models


class ABSModel(saffier.StrictModel):
    id = fields.IntegerField(primary_key=True, autoincrement=True)

    class Meta:
        abstract = True
        registry = models
        table_prefix = "abs"


class InheritABSModel(ABSModel):
    name = fields.CharField(null=True, max_length=255)

    class Meta:
        registry = models


class SecondInheritABSModel(InheritABSModel):
    description = fields.CharField(null=True, max_length=255)

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


async def test_table_prefix():
    assert Product.table.name == "test_products"
    assert InheritProduct.table.name == "test_inheritproducts"
    assert InheritABSModel.table.name == "abs_inheritabsmodels"
    assert SecondInheritABSModel.table.name == "abs_secondinheritabsmodels"
