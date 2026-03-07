import pytest

import saffier
from saffier.contrib.contenttypes import ContentTypeField
from saffier.contrib.contenttypes.models import ContentType as BaseContentType
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL, use_existing=True)


class ExplicitContentType(BaseContentType):
    custom_field = saffier.CharField(max_length=1, null=True)
    hidden_field = saffier.CharField(max_length=1, null=True, inherit=False)

    class Meta:
        abstract = True


models = saffier.Registry(database=database, with_content_type=ExplicitContentType)


class Company(saffier.Model):
    name = saffier.CharField(max_length=100, unique=True)

    class Meta:
        registry = models


class Person(saffier.Model):
    first_name = saffier.CharField(max_length=100)
    last_name = saffier.CharField(max_length=100)
    c = ContentTypeField()

    class Meta:
        registry = models
        unique_together = [("first_name", "last_name")]


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    async with database:
        await models.create_all()
        yield
        if not database.drop:
            await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connections():
    async with models:
        yield


async def test_registry_uses_concrete_custom_content_type():
    assert models.content_type is models.get_model("ContentType", include_content_type_attr=False)
    assert "custom_field" in models.content_type.meta.fields
    assert "hidden_field" not in models.content_type.meta.fields


async def test_custom_abstract_content_type_field_defaults_to_registry_model():
    company = await Company.query.create(name="abstract-custom")
    person = await Person.query.create(first_name="Ada", last_name="Lovelace", c={})

    assert company.content_type.name == "Company"
    assert person.c.name == "Person"
    assert await person.c.get_instance() == person
