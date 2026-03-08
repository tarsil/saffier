import pytest

import saffier
from saffier.contrib.contenttypes import ContentTypeField
from saffier.contrib.contenttypes.models import ContentType as BaseContentType
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_ALTERNATIVE_URL, DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL, use_existing=True)
database2 = DatabaseTestClient(DATABASE_ALTERNATIVE_URL, use_existing=True)


class ExplicitContentType(BaseContentType):
    class Meta:
        abstract = True


shared_models = saffier.Registry(database=database2, with_content_type=ExplicitContentType)
models = saffier.Registry(database=database, with_content_type=shared_models.content_type)


class Company(saffier.Model):
    name = saffier.CharField(max_length=100, unique=True)

    class Meta:
        registry = models


class Organisation(saffier.Model):
    name = saffier.CharField(max_length=100, unique=True)

    class Meta:
        registry = models


class Person(saffier.Model):
    name = saffier.CharField(max_length=100)
    c = ContentTypeField()

    class Meta:
        registry = models


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    async with database, database2:
        await shared_models.create_all()
        await models.create_all()
        yield
        if not database.drop:
            await models.drop_all()
        if not database2.drop:
            await shared_models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_transactions():
    async with models, shared_models:
        await Person.query.raw_delete()
        await Company.query.raw_delete()
        await Organisation.query.raw_delete()
        await shared_models.content_type.query.raw_delete()
        yield
        await Person.query.raw_delete()
        await Company.query.raw_delete()
        await Organisation.query.raw_delete()
        await shared_models.content_type.query.raw_delete()


async def test_registry_reuses_external_content_type_model():
    assert models.content_type is shared_models.get_model(
        "ContentType", include_content_type_attr=False
    )


async def test_default_contenttypes_are_stored_in_shared_registry():
    company = await Company.query.create(name="shared-company")
    organisation = await Organisation.query.create(name="shared-organisation")

    assert company.content_type.name == "Company"
    assert organisation.content_type.name == "Organisation"
    assert await shared_models.content_type.query.count() == 2

    loaded = await shared_models.content_type.query.get(id=company.content_type.id)
    assert await loaded.get_instance() == company


async def test_content_type_field_default_target_uses_external_content_type():
    person = await Person.query.create(name="external-target", c={})
    loaded = await Person.query.get(id=person.id)

    assert loaded.c.name == "Person"
    assert await loaded.c.get_instance() == person
    assert await shared_models.content_type.query.filter(id=loaded.c.id).count() == 1


async def test_deleting_shared_content_types_cascades_referencing_models():
    company = await Company.query.create(name="cascade-company")
    await Organisation.query.create(name="cascade-organisation")

    assert await Company.query.filter(id=company.id).count() == 1
    assert await Organisation.query.count() == 1

    await models.content_type.query.delete()

    assert await Company.query.count() == 0
    assert await Organisation.query.count() == 0
