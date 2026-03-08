import datetime
import decimal
from enum import Enum

import pytest
import sqlalchemy

import saffier
from saffier.core.db import fields
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL)
models = saffier.Registry(database=database)


class StatusEnum(Enum):
    DRAFT = "Draft"
    RELEASED = "Released"


class SimpleProduct(saffier.StrictModel):
    active = fields.BooleanField(null=True)
    description = fields.CharField(null=True, max_length=255)
    integer = fields.IntegerField(null=True)
    price = fields.DecimalField(max_digits=9, decimal_places=2, null=True)
    value = fields.FloatField(null=True)

    class Meta:
        registry = models


class Product(saffier.StrictModel):
    active = fields.BooleanField(null=True)
    description = fields.CharField(null=True, max_length=255)
    integer = fields.IntegerField(null=True)
    price = fields.DecimalField(max_digits=9, decimal_places=2, null=True)
    value = fields.FloatField(null=True)
    binary = fields.BinaryField(null=True)
    duration = fields.DurationField(null=True)
    created = fields.DateTimeField(null=True)
    created_date = fields.DateField(null=True)
    created_time = fields.TimeField(null=True)
    uuid = fields.UUIDField(null=True)
    data = fields.JSONField(null=True)
    status = fields.ChoiceField(StatusEnum, null=True)
    manual = fields.FileField(null=True)
    ipaddress = fields.IPAddressField(null=True)

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True, scope="function")
async def rollback_transactions():
    with database.force_rollback():
        async with database:
            yield


@pytest.mark.parametrize(
    "product,isnull",
    [
        pytest.param(SimpleProduct(), True),
        pytest.param(
            SimpleProduct(description="", integer=0, price=decimal.Decimal("0"), value=0.0),
            False,
        ),
        pytest.param(
            Product(),
            True,
        ),
        pytest.param(
            Product(
                active=False,
                duration=datetime.timedelta(),
                description="",
                integer=0,
                price=decimal.Decimal("0.0"),
                value=0.0,
                binary=b"",
            ),
            False,
        ),
    ],
)
async def test_operators_empty(product, isnull):
    await product.save()
    isempty_queries = {}
    isnull_queries = {}
    for field_name, field in product.meta.fields.items():
        if field.primary_key or field.exclude:
            continue
        isempty_queries[f"{field_name}__isempty"] = True
        isnull_queries[f"{field_name}__isnull"] = True
    assert await type(product).query.exists(**isempty_queries)
    assert (await type(product).query.exists(**isnull_queries)) == isnull


@pytest.mark.parametrize(
    "product,isempty,isnull",
    [
        pytest.param(Product(), True, True),
        pytest.param(Product(data=sqlalchemy.null()), True, True),
        pytest.param(Product(data=sqlalchemy.JSON.NULL), True, True),
        pytest.param(Product(data=""), True, False),
        pytest.param(Product(data=[]), True, False),
        pytest.param(Product(data={}), True, False),
        pytest.param(Product(data=0), True, False),
        pytest.param(Product(data=0.0), True, False),
    ],
)
async def test_operators_empty_json(product, isempty, isnull):
    await product.save()

    assert (await type(product).query.exists(data__isempty=True)) == isempty
    assert (await type(product).query.exists(data__isnull=True)) == isnull

    assert (await type(product).query.exists(data__isempty=False)) != isempty
    assert (await type(product).query.exists(data__isnull=False)) != isnull


@pytest.mark.parametrize("field_name", ["created", "created_date", "ipaddress"])
async def test_troubled_none(field_name):
    product = await Product.query.create()
    assert await type(product).query.exists(**{field_name: None})
