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


async def test_non_abstract_content_type_is_reused_directly():
    assert models.content_type is ExplicitContentType
    assert models.content_type is models.get_model("ContentType", include_content_type_attr=False)
    assert "custom_field" in models.content_type.meta.fields


async def test_non_abstract_custom_content_type_keeps_default_field_resolution():
    company = await Company.query.create(name="non-abstract-custom")
    person = await Person.query.create(first_name="Grace", last_name="Hopper", c={})

    assert company.content_type.name == "Company"
    assert person.c.name == "Person"
    assert await person.c.get_instance() == person
