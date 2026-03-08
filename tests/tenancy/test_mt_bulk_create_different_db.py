import copy
from datetime import datetime
from enum import Enum

import pytest

import saffier
from saffier.core.db import fields
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_ALTERNATIVE_URL, DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
another_db = Database(DATABASE_ALTERNATIVE_URL)
models = saffier.Registry(database=database, extra={"another": another_db})


def time():
    return datetime.now().time()


class StatusEnum(Enum):
    DRAFT = "Draft"
    RELEASED = "Released"


class Product(saffier.Model):
    id = fields.IntegerField(primary_key=True)
    data = fields.JSONField(default={})
    status = fields.ChoiceField(StatusEnum, default=StatusEnum.DRAFT)
    value = fields.FloatField(null=True)

    class Meta:
        registry = models


registry = copy.copy(models)
registry.database = another_db
for model in registry.models.values():
    model.database = another_db


async def setup_databases() -> None:
    await models.create_all()
    registry.metadata_by_name = models.metadata_by_name.copy()
    await registry.create_all(refresh_metadata=False)


async def teardown_databases() -> None:
    await registry.drop_all()
    await models.drop_all()
    for db in {database, another_db, registry.database}:
        if db.is_connected:
            await db.disconnect()


async def test_bulk_create_another_tenant():
    await setup_databases()
    try:
        await Product.query.using(database="another").bulk_create(
            [
                {"data": {"foo": 123}, "value": 123.456, "status": StatusEnum.RELEASED},
                {"data": {"foo": 456}, "value": 456.789, "status": StatusEnum.DRAFT},
            ]
        )

        products = await Product.query.all()
        assert len(products) == 0

        others = await Product.query.using(database="another").all()
        assert len(others) == 2
    finally:
        await teardown_databases()


async def test_bulk_create_another_schema_and_db():
    await setup_databases()
    try:
        await registry.schema.create_schema("foo", init_models=True, if_not_exists=True)
        await Product.query.using(database="another", schema="foo").bulk_create(
            [
                {"data": {"foo": 123}, "value": 123.456, "status": StatusEnum.RELEASED},
                {"data": {"foo": 456}, "value": 456.789, "status": StatusEnum.DRAFT},
            ]
        )

        products = await Product.query.all()
        assert len(products) == 0

        products = await Product.query.using(database="another").all()
        assert len(products) == 0

        others = await Product.query.using(database="another", schema="foo").all()
        assert len(others) == 2
    finally:
        await registry.schema.drop_schema("foo", cascade=True, if_exists=True)
        await teardown_databases()
