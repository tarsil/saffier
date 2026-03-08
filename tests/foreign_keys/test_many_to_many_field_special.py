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
        tablename = "special_m2m_user"


class Studio(saffier.Model):
    name = saffier.CharField(max_length=255)
    users = saffier.ManyToMany(
        User,
        through_tablename="foo",
        to_foreign_key="usr",
        from_foreign_key="fromage",
    )

    class Meta:
        registry = models
        tablename = "special_m2m_studio"


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


async def test_check_tablename_and_custom_foreign_keys():
    through = Studio.meta.fields["users"].through

    assert through.meta.tablename == "foo"
    assert Studio.meta.fields["users"].from_foreign_key == "fromage"
    assert Studio.meta.fields["users"].to_foreign_key == "usr"


async def test_many_to_many_many_fields():
    user1 = await User.query.create(name="Charlie")
    user2 = await User.query.create(name="Monica")
    user3 = await User.query.create(name="Snoopy")

    studio = await Studio.query.create(name="Downtown Records")
    await studio.users.add(user1)
    await studio.users.add(user2)
    await studio.users.add(user3)

    total_users = await studio.users.all()

    assert len(total_users) == 3
    assert [user.pk for user in total_users] == [user1.pk, user2.pk, user3.pk]
