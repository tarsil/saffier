import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio
TABLE_PREFIX = "fkembed"

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class Address(saffier.StrictModel):
    street = saffier.CharField(max_length=100)
    city = saffier.CharField(max_length=100)

    class Meta:
        abstract = True
        registry = models


class Person(saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    email = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        table_prefix = TABLE_PREFIX


class Profile(saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    website = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        table_prefix = TABLE_PREFIX


class ProfileHolder(saffier.StrictModel):
    address = Address
    profile = saffier.OneToOneField(
        Profile, on_delete=saffier.CASCADE, embed_parent=("address", "parent")
    )
    person = saffier.OneToOneField(
        Person,
        on_delete=saffier.CASCADE,
        embed_parent=("profile", "parent"),
        related_name="profile_holder",
    )
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        table_prefix = TABLE_PREFIX


class EmbeddedProfile(saffier.StrictModel):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    website = saffier.CharField(max_length=100)
    address = Address

    class Meta:
        registry = models
        table_prefix = f"{TABLE_PREFIX}deep"


class EmbeddedProfileHolder(saffier.StrictModel):
    profile = saffier.OneToOneField(EmbeddedProfile, on_delete=saffier.CASCADE)
    person = saffier.OneToOneField(
        Person,
        on_delete=saffier.CASCADE,
        embed_parent=("profile__address", "parent"),
        related_name="address",
    )
    name = saffier.CharField(max_length=100)

    class Meta:
        registry = models
        table_prefix = f"{TABLE_PREFIX}deep"


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


async def test_embed_parent():
    profile = await Profile.query.create(website="https://saffier.com")
    person = await Person.query.create(email="info@saffier.com")
    profile_holder = await ProfileHolder.query.create(
        name="saffier",
        profile=profile,
        person=person,
        address={"street": "Rainbowstreet 123", "city": "London"},
    )

    person = await Person.query.get(email="info@saffier.com")
    profile_queried = await person.profile_holder.get()
    assert profile_queried.pk == profile.pk
    assert profile_queried.website == "https://saffier.com"
    await profile_queried.parent.load()
    assert profile_queried.parent.name == "saffier"
    assert profile_queried.pk == (await person.profile_holder.filter(parent__name="saffier").get()).pk

    address_queried = await profile.profileholder.get()
    assert address_queried.street == "Rainbowstreet 123"
    await address_queried.parent.load()
    assert address_queried.parent.name == profile_holder.name
    assert address_queried.parent.pk == profile_holder.pk
    assert await profile.profileholder.filter(address_city="London").exists()


async def test_embed_parent_deep():
    profile = await EmbeddedProfile.query.create(
        website="https://saffier.com",
        address={"street": "Rainbowstreet 123", "city": "London"},
    )
    person = await Person.query.create(email="info-deep@saffier.com")
    profile_holder = await EmbeddedProfileHolder.query.create(
        name="saffier",
        profile=profile,
        person=person,
    )

    person = await Person.query.get(email="info-deep@saffier.com")
    address_queried = await person.address.get()
    assert address_queried.street == "Rainbowstreet 123"
    await address_queried.parent.load()
    assert address_queried.parent.name == profile_holder.name
    assert address_queried.parent.pk == profile_holder.pk
