import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)

pytestmark = pytest.mark.anyio


class User(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)
    number = saffier.IntegerField()
    profile_name = saffier.PlaceholderField(null=True)

    class Meta:
        registry = models
        table_prefix = "xembed"


class Profile(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    user = saffier.OneToOneField(User, related_name="profile")
    name = saffier.CharField(max_length=100)
    profile = saffier.OneToOneField(
        "SuperProfile",
        related_name="profile",
        embed_parent=("user", "normal_profile"),
    )

    class Meta:
        registry = models
        table_prefix = "xembed"


class SuperProfile(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        table_prefix = "xembed"


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
                super_profile = await SuperProfile.query.create(name=f"super-{idx}")
                await Profile.query.create(
                    user=user,
                    name=f"profile-{idx}",
                    profile=super_profile,
                )
            yield


async def test_embed_parent_returns_user_with_embedded_profile():
    for super_profile in await SuperProfile.query.all():
        user = await super_profile.profile.reference_select(
            {"user": {"profile_name": "name"}}
        ).get()

        assert issubclass(user.get_real_class(), User)
        assert user.normal_profile.name == user.profile_name


async def test_embed_parent_all_returns_embedded_users():
    super_profile = await SuperProfile.query.order_by("id").first()
    assert super_profile is not None
    users = await super_profile.profile.all()

    assert len(users) == 1
    assert issubclass(users[0].get_real_class(), User)
    assert users[0].normal_profile.profile.pk == super_profile.pk


async def test_embed_parent_filter_uses_embedded_parent_path():
    super_profile = await SuperProfile.query.order_by("id").first()
    assert super_profile is not None

    users = await super_profile.profile.filter(name="user-0")

    assert len(users) == 1
    assert users[0].name == "user-0"


async def test_embed_parent_filter_supports_parent_prefix():
    super_profile = await SuperProfile.query.order_by("id").first()
    assert super_profile is not None

    users = await super_profile.profile.filter(normal_profile__name="profile-0")

    assert len(users) == 1
    assert users[0].normal_profile.name == "profile-0"
