import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        tablename = "new_naming_user"


class Studio(saffier.Model):
    name = saffier.CharField(max_length=255)
    users = saffier.ManyToMany(User)
    admins = saffier.ManyToMany(User)

    class Meta:
        registry = models
        tablename = "new_naming_studio"


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connections():
    with database.force_rollback():
        async with database:
            yield


async def test_check_tablename():
    assert Studio.meta.fields["users"].through.meta.tablename == "studiousersthrough"
    assert Studio.meta.fields["admins"].through.meta.tablename == "studioadminsthrough"


async def test_many_to_many_many_fields():
    user1 = await User.query.create(name="Charlie")
    user2 = await User.query.create(name="Monica")
    user3 = await User.query.create(name="Snoopy")

    studio = await Studio.query.create(name="Downtown Records")
    await studio.users.add(user1)
    await studio.users.add(user2)
    await studio.admins.add(user2)
    await studio.users.add(user3)

    total_users = await studio.users.all()
    assert len(total_users) == 3
    assert [user.pk for user in total_users] == [user1.pk, user2.pk, user3.pk]

    total_admins = await studio.admins.all()
    assert len(total_admins) == 1
    assert total_admins[0].pk == user2.pk
