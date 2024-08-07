from datetime import datetime
from enum import Enum

import pytest
from sqlalchemy.exc import ProgrammingError

import saffier
from saffier.core.db import fields
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


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
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_transactions():
    with database.force_rollback():
        async with database:
            yield


async def test_bulk_create_another_tenant():
    with pytest.raises(ProgrammingError):
        await Product.query.using("another").bulk_create(
            [
                {"data": {"foo": 123}, "value": 123.456, "status": StatusEnum.RELEASED},
                {"data": {"foo": 456}, "value": 456.789, "status": StatusEnum.DRAFT},
            ]
        )
