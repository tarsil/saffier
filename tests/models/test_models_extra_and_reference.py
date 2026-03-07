import pytest
import sqlalchemy

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class User(saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)
    number = saffier.IntegerField()
    profile_name = saffier.PlaceholderField(null=True)

    class Meta:
        registry = models
        table_prefix = "xref"


class Profile(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    user = saffier.OneToOneField(User, related_name="profile")
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        table_prefix = "xref"


class SuperProfile(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    profile = saffier.OneToOneField(Profile, related_name="profile")
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        table_prefix = "xref"


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True, scope="function")
async def rollback_transactions():
    with database.force_rollback():
        async with database:
            for idx in range(10):
                user = await User.query.create(name=f"user-{idx}", number=10)
                profile = await Profile.query.create(user=user, name=f"profile-{idx}")
                await SuperProfile.query.create(profile=profile, name=f"super-{idx}")
            yield


async def test_basic_referencing_relaxed_related():
    for super_profile in await SuperProfile.query.select_related("profile").reference_select(
        {"profile": {"profile_name": "name"}}
    ):
        assert super_profile.profile.profile_name == super_profile.name


async def test_annotate_parent():
    for profile in await Profile.query.select_related("user").reference_select(
        {"user_name": "user__name"}
    ):
        assert profile.user_name == profile.user.name


async def test_annotate_parent_with_column_source():
    for profile in await Profile.query.select_related("user").reference_select(
        {"user_name": User.table.c.name}
    ):
        assert profile.user_name == profile.user.name


async def test_basic_referencing_relaxed_fk():
    for super_profile in await SuperProfile.query.reference_select(
        {"profile": {"profile_name": "name"}}
    ):
        assert super_profile.profile.profile_name == super_profile.name


async def test_basic_referencing_strict_related():
    for profile in await Profile.query.select_related("user").reference_select(
        {"user": {"profile_name": "name"}}
    ):
        assert profile.user.profile_name == profile.name


async def test_basic_referencing_strict_fk():
    for profile in await Profile.query.reference_select({"user": {"profile_name": "name"}}):
        assert profile.user.profile_name == profile.name


async def test_overwrite():
    for profile in await Profile.query.select_related("user").reference_select(
        {"user": {"name": "name"}}
    ):
        assert profile.user.name == profile.name


async def test_reference_select_with_get_or_none():
    profile = await (
        Profile.query.filter(name="profile-0")
        .select_related("user")
        .reference_select({"user": {"profile_name": "name"}})
        .get_or_none()
    )

    assert profile is not None
    assert profile.user.profile_name == profile.name


async def test_counting_query():
    total_query = (
        sqlalchemy.func.count()
        .select()
        .select_from((await User.query.as_select()).subquery())
        .label("total_number")
    )

    for profile in await Profile.query.extra_select(total_query).reference_select(
        {"total_number": "total_number"}
    ):
        assert profile.total_number == 10


async def test_summing_query():
    total_query = sqlalchemy.select(sqlalchemy.func.sum(User.table.c.number)).scalar_subquery()

    for profile in await Profile.query.extra_select(total_query.label("total_number")).reference_select(
        {"total_number": "total_number"}
    ):
        assert profile.total_number == 100
