import datetime
from enum import Enum

import pytest
from sqlalchemy.exc import IntegrityError

import saffier
from saffier.core.db.datastructures import UniqueConstraint
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


def time():
    return datetime.datetime.now().time()


class StatusEnum(Enum):
    DRAFT = "Draft"
    RELEASED = "Released"


class BaseModel(saffier.Model):
    class Meta:
        registry = models


class User(BaseModel):
    name = saffier.CharField(max_length=255)
    email = saffier.CharField(max_length=60)

    class Meta:
        unique_together = [UniqueConstraint(fields=["name", "email"])]


class HubUser(BaseModel):
    name = saffier.CharField(max_length=255)
    email = saffier.CharField(max_length=60, null=True)
    age = saffier.IntegerField(minimum=18, null=True)

    class Meta:
        unique_together = [
            UniqueConstraint(fields=["name", "email"]),
            ("email", "age"),
        ]


class Product(BaseModel):
    name = saffier.CharField(max_length=255)
    sku = saffier.CharField(max_length=255)

    class Meta:
        unique_together = [UniqueConstraint(fields=["name"]), UniqueConstraint(fields=["sku"])]


class NewProduct(BaseModel):
    name = saffier.CharField(max_length=255)
    sku = saffier.CharField(max_length=255)

    class Meta:
        unique_together = [UniqueConstraint(fields=["name"]), "sku"]


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


@pytest.mark.skipif(database.url.dialect == "mysql", reason="Not supported on MySQL")
async def test_unique_together():
    await User.query.create(name="Test", email="test@example.com")
    await User.query.create(name="Test", email="test2@example.come")

    with pytest.raises(IntegrityError):
        await User.query.create(name="Test", email="test@example.com")


@pytest.mark.skipif(database.url.dialect == "mysql", reason="Not supported on MySQL")
async def test_unique_together_multiple():
    await HubUser.query.create(name="Test", email="test@example.com")
    await HubUser.query.create(name="Test", email="test2@example.come")

    with pytest.raises(IntegrityError):
        await HubUser.query.create(name="Test", email="test@example.com")


@pytest.mark.skipif(database.url.dialect == "mysql", reason="Not supported on MySQL")
async def test_unique_together_multiple_name_age():
    await HubUser.query.create(name="NewTest", email="test@example.com", age=18)

    with pytest.raises(IntegrityError):
        await HubUser.query.create(name="Test", email="test@example.com", age=18)


@pytest.mark.skipif(database.url.dialect == "mysql", reason="Not supported on MySQL")
async def test_unique_together_multiple_single_string():
    await Product.query.create(name="android", sku="12345")

    with pytest.raises(IntegrityError):
        await Product.query.create(name="android", sku="12345")


@pytest.mark.skipif(database.url.dialect == "mysql", reason="Not supported on MySQL")
async def test_unique_together_multiple_single_string_two():
    await Product.query.create(name="android", sku="12345")

    with pytest.raises(IntegrityError):
        await Product.query.create(name="iphone", sku="12345")
