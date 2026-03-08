import pytest
import sqlalchemy
from sqlalchemy import exc

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(url=DATABASE_URL)
models = saffier.Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=255)
    is_admin = saffier.BooleanField(default=False)
    age = saffier.IntegerField(null=True)

    class Meta:
        registry = models
        tablename = "constraint_users"
        constraints = [sqlalchemy.CheckConstraint("age > 13 OR is_admin = true", name="user_age")]


class AbstractConstrained(saffier.Model):
    amount = saffier.IntegerField()

    class Meta:
        abstract = True
        constraints = [sqlalchemy.CheckConstraint("amount >= 0", name="amount_positive")]


class Ledger(AbstractConstrained):
    class Meta:
        registry = models
        tablename = "constraint_ledgers"


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


async def test_create_user():
    user = await User.query.create(name="Test", is_admin=False, age=20)
    assert user.age == 20


async def test_create_admin():
    user = await User.query.create(name="Test", is_admin=True)
    assert user.age is None


async def test_fail_create_user():
    with pytest.raises(exc.IntegrityError):
        await User.query.create(name="Test", is_admin=False, age=1)


async def test_inherits_abstract_constraints():
    ledger = await Ledger.query.create(amount=0)
    assert ledger.amount == 0

    with pytest.raises(exc.IntegrityError):
        await Ledger.query.create(amount=-1)
