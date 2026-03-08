import pytest
from sqlalchemy.exc import IntegrityError

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)


class BaseModel(saffier.Model):
    class Meta:
        registry = models


class AbsUser(saffier.Model):
    name = saffier.CharField(max_length=255, index=True)
    email = saffier.CharField(max_length=60)

    class Meta:
        abstract = True
        unique_together = [("name", "email")]


class User(AbsUser, BaseModel):
    class Meta:
        registry = models
        tablename = "unique_together_inherit_users"


class AbsHubUser(saffier.Model):
    name = saffier.CharField(max_length=255)
    title = saffier.CharField(max_length=255, null=True)
    description = saffier.CharField(max_length=255, null=True)

    class Meta:
        abstract = True
        unique_together = [("name", "email"), ("email", "age")]


class HubUser(AbsHubUser, BaseModel):
    name = saffier.CharField(max_length=255)
    email = saffier.CharField(max_length=60, null=True)
    age = saffier.IntegerField(minimum=18, null=True)

    class Meta:
        registry = models
        tablename = "unique_together_inherit_hubusers"


class AbsProduct(saffier.Model):
    name = saffier.CharField(max_length=255)
    sku = saffier.CharField(max_length=255)

    class Meta:
        abstract = True
        unique_together = ["name", "sku"]


class Product(AbsProduct, BaseModel):
    class Meta:
        registry = models
        tablename = "unique_together_inherit_products"


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
    await User.query.create(name="Test", email="test2@example.com")

    with pytest.raises(IntegrityError):
        await User.query.create(name="Test", email="test@example.com")


@pytest.mark.skipif(database.url.dialect == "mysql", reason="Not supported on MySQL")
async def test_unique_together_multiple():
    await HubUser.query.create(name="Test", email="test@example.com")
    await HubUser.query.create(name="Test", email="test2@example.com")

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
