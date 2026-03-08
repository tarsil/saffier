import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

database = Database(url=DATABASE_URL)
plain_models = saffier.Registry(database=database)
engine_models = saffier.Registry(database=database, model_engine="pydantic")
msgspec_models = saffier.Registry(database=database, model_engine="msgspec")

pytestmark = pytest.mark.anyio


class PlainProfile(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = plain_models
        table_prefix = "plain_engine"


class PlainUser(saffier.Model):
    email = saffier.EmailField(max_length=255)
    profile = saffier.ForeignKey(PlainProfile, on_delete=saffier.CASCADE)

    class Meta:
        registry = plain_models
        table_prefix = "plain_engine"


class PlainOrganisation(saffier.Model):
    user = saffier.ForeignKey(PlainUser, on_delete=saffier.CASCADE)
    label = saffier.CharField(max_length=100)

    class Meta:
        registry = plain_models
        table_prefix = "plain_engine"


class EngineProfile(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = engine_models
        table_prefix = "pydantic_engine"


class EngineUser(saffier.Model):
    email = saffier.EmailField(max_length=255)
    profile = saffier.ForeignKey(EngineProfile, on_delete=saffier.CASCADE)

    class Meta:
        registry = engine_models
        table_prefix = "pydantic_engine"


class EngineOrganisation(saffier.Model):
    user = saffier.ForeignKey(EngineUser, on_delete=saffier.CASCADE)
    label = saffier.CharField(max_length=100)

    class Meta:
        registry = engine_models
        table_prefix = "pydantic_engine"


class MsgspecProfile(saffier.Model):
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = msgspec_models
        table_prefix = "msgspec_engine"


class MsgspecUser(saffier.Model):
    email = saffier.EmailField(max_length=255)
    profile = saffier.ForeignKey(MsgspecProfile, on_delete=saffier.CASCADE)

    class Meta:
        registry = msgspec_models
        table_prefix = "msgspec_engine"


class MsgspecOrganisation(saffier.Model):
    user = saffier.ForeignKey(MsgspecUser, on_delete=saffier.CASCADE)
    label = saffier.CharField(max_length=100)

    class Meta:
        registry = msgspec_models
        table_prefix = "msgspec_engine"


@pytest.fixture(autouse=True, scope="function")
async def create_test_database():
    await plain_models.create_all()
    await engine_models.create_all()
    await msgspec_models.create_all()
    yield
    await msgspec_models.drop_all()
    await engine_models.drop_all()
    await plain_models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connections():
    with database.force_rollback():
        async with database:
            yield


async def test_plain_queryset_and_relations_are_unchanged_without_engine() -> None:
    profile = await PlainProfile.query.create(name="plain")
    user = await PlainUser.query.create(email="plain@example.com", profile=profile)
    await PlainOrganisation.query.create(user=user, label="plain-org")

    organisation = await PlainOrganisation.query.select_related("user__profile").get()

    assert isinstance(organisation, PlainOrganisation)
    assert isinstance(organisation.user, PlainUser)
    assert isinstance(organisation.user.profile, PlainProfile)
    assert organisation.model_dump() == {
        "id": 1,
        "user": {
            "id": 1,
            "email": "plain@example.com",
            "profile": {"id": 1, "name": "plain"},
        },
        "label": "plain-org",
    }


async def test_engine_configured_queryset_and_relations_keep_core_model_behavior() -> None:
    profile = await EngineProfile.query.create(name="pydantic")
    user = await EngineUser.query.create(email="pydantic@example.com", profile=profile)
    await EngineOrganisation.query.create(user=user, label="pydantic-org")

    organisation = await EngineOrganisation.query.select_related("user__profile").get()
    projected_user = organisation.user.to_engine_model()

    assert isinstance(organisation, EngineOrganisation)
    assert isinstance(organisation.user, EngineUser)
    assert isinstance(organisation.user.profile, EngineProfile)
    assert organisation.model_dump() == {
        "id": 1,
        "user": {
            "id": 1,
            "email": "pydantic@example.com",
            "profile": {"id": 1, "name": "pydantic"},
        },
        "label": "pydantic-org",
    }
    assert projected_user.model_dump(exclude_unset=True) == {
        "id": 1,
        "email": "pydantic@example.com",
        "profile": {"id": 1, "name": "pydantic"},
    }


async def test_engine_configuration_does_not_change_query_update_or_count_behavior() -> None:
    profile = await EngineProfile.query.create(name="initial")
    user = await EngineUser.query.create(email="count@example.com", profile=profile)

    user.email = "updated@example.com"
    await user.save()

    assert await EngineUser.query.count() == 1
    assert await EngineUser.query.filter(email="updated@example.com").exists() is True

    loaded = await EngineUser.query.select_related("profile").get(email="updated@example.com")
    assert loaded.profile.name == "initial"
    assert loaded.engine_dump() == {
        "id": loaded.id,
        "email": "updated@example.com",
        "profile": {"id": profile.id, "name": "initial"},
    }


async def test_msgspec_engine_queryset_and_relations_keep_core_model_behavior() -> None:
    profile = await MsgspecProfile.query.create(name="msgspec")
    user = await MsgspecUser.query.create(email="msgspec@example.com", profile=profile)
    await MsgspecOrganisation.query.create(user=user, label="msgspec-org")

    organisation = await MsgspecOrganisation.query.select_related("user__profile").get()
    projected_user = organisation.user.to_engine_model()

    assert isinstance(organisation, MsgspecOrganisation)
    assert isinstance(organisation.user, MsgspecUser)
    assert isinstance(organisation.user.profile, MsgspecProfile)
    assert hasattr(type(projected_user), "__struct_fields__")
    assert organisation.model_dump() == {
        "id": 1,
        "user": {
            "id": 1,
            "email": "msgspec@example.com",
            "profile": {"id": 1, "name": "msgspec"},
        },
        "label": "msgspec-org",
    }
    assert organisation.user.engine_dump() == {
        "id": 1,
        "email": "msgspec@example.com",
        "profile": {"id": 1, "name": "msgspec"},
    }
    assert '"email":"msgspec@example.com"' in organisation.user.engine_dump_json()
