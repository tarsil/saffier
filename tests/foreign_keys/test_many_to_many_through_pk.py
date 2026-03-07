import pytest

import saffier
from saffier.exceptions import ImproperlyConfigured
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio


database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models


class Group(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)
    users = saffier.ManyToManyField(User)

    class Meta:
        registry = models


@pytest.fixture(scope="function")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture
async def rollback_connections():
    with database.force_rollback():
        async with database:
            yield


def build_registry() -> saffier.Registry:
    return saffier.Registry(database=Database(url=DATABASE_URL))


def test_auto_through_model_has_autoincrementing_id_pk() -> None:
    through = Group.meta.fields["users"].through

    assert through is not None
    assert through.pkname == "id"
    assert tuple(through.pknames) == ("id",)
    assert tuple(through.pkcolumns) == ("id",)

    id_field = through.fields["id"]
    assert id_field.primary_key is True
    assert id_field.autoincrement is True


@pytest.mark.usefixtures("create_test_database", "rollback_connections")
async def test_auto_through_rows_have_incrementing_ids() -> None:
    user_one = await User.query.create(name="one")
    user_two = await User.query.create(name="two")
    group = await Group.query.create(name="group")

    await group.users.add(user_one)
    await group.users.add(user_two)

    through = Group.meta.fields["users"].through
    expression = through.table.select()  # type: ignore[union-attr]
    rows = await through.query.database.fetch_all(expression)  # type: ignore[union-attr]
    through_ids = sorted([row._mapping["id"] for row in rows])

    assert len(through_ids) == 2
    assert all(identifier is not None for identifier in through_ids)
    assert through_ids[0] != through_ids[1]


@pytest.mark.usefixtures("create_test_database", "rollback_connections")
async def test_create_with_many_to_many_values_persists_rows_with_ids() -> None:
    user_one = await User.query.create(name="alpha")
    user_two = await User.query.create(name="beta")

    group = await Group.query.create(name="crew", users=[user_one, user_two])
    related_users = await group.users.all()
    related_ids = sorted(user.pk for user in related_users)

    through = Group.meta.fields["users"].through
    expression = through.table.select()  # type: ignore[union-attr]
    rows = await through.query.database.fetch_all(expression)  # type: ignore[union-attr]
    through_ids = sorted(row._mapping["id"] for row in rows)

    assert related_ids == [user_one.pk, user_two.pk]
    assert len(through_ids) == 2
    assert through_ids[0] > 0
    assert through_ids[0] != through_ids[1]


def test_custom_through_model_without_primary_key_gets_id() -> None:
    registry_obj = build_registry()

    class Member(saffier.Model):
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = registry_obj

    class Membership(saffier.Model):
        member = saffier.ForeignKey(Member, null=False, on_delete=saffier.CASCADE)

        class Meta:
            registry = registry_obj

    class Team(saffier.Model):
        name = saffier.CharField(max_length=100)
        members = saffier.ManyToManyField(Member, through=Membership)

        class Meta:
            registry = registry_obj

    assert Team.meta.fields["members"].through is Membership
    assert Membership.pkname == "id"
    assert Membership.fields["id"].primary_key is True
    assert Membership.fields["id"].autoincrement is True


def test_custom_through_model_with_non_id_primary_key_is_rejected() -> None:
    registry_obj = build_registry()

    class Member(saffier.Model):
        name = saffier.CharField(max_length=100)

        class Meta:
            registry = registry_obj

    class MembershipBad(saffier.Model):
        id = saffier.IntegerField(primary_key=False)
        token = saffier.IntegerField(primary_key=True)
        member = saffier.ForeignKey(Member, null=False, on_delete=saffier.CASCADE)

        class Meta:
            registry = registry_obj

    with pytest.raises(
        ImproperlyConfigured,
        match="ManyToMany through models must .*'id'.*primary key",
    ):

        class Team(saffier.Model):
            name = saffier.CharField(max_length=100)
            members = saffier.ManyToManyField(Member, through=MembershipBad)

            class Meta:
                registry = registry_obj
