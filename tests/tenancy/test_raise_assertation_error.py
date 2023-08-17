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
registry = copy.copy(models)
registry.database = another_db


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


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    await registry.create_all()
    yield
    await models.drop_all()
    await registry.drop_all()


@pytest.fixture(autouse=True)
async def rollback_transactions():
    with database.force_rollback():
        async with database:
            yield


@pytest.fixture(autouse=True)
async def rollback_another_db_transactions():
    with another_db.force_rollback():
        async with another_db:
            yield


async def test_bulk_create_another_tenant():
    with pytest.raises(AssertionError):
        await Product.query.using_with_db("saffier").bulk_create(
            [
                {"data": {"foo": 123}, "value": 123.456, "status": StatusEnum.RELEASED},
                {"data": {"foo": 456}, "value": 456.789, "status": StatusEnum.DRAFT},
            ]
        )
