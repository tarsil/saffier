import pytest
from sqlalchemy.exc import IntegrityError

import saffier
from saffier.contrib.contenttypes import ContentTypeField
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL, use_existing=False)
models = saffier.Registry(database=database, with_content_type=True)


class ContentTypeTag(saffier.Model):
    ctype = saffier.ForeignKey(to="ContentType", related_name="tags", on_delete=saffier.CASCADE)
    tag = saffier.CharField(max_length=50)
    content_type = saffier.ExcludeField()

    class Meta:
        registry = models


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
    async with database:
        await models.create_all()
        yield
        if not database.drop:
            await models.drop_all()


@pytest.fixture(autouse=True, scope="function")
async def rollback_transactions():
    async with models:
        yield


async def test_registry_content_type_setup():
    assert models.content_type is models.get_model("ContentType")
    assert Company.meta.fields["content_type"].on_delete == saffier.CASCADE
    assert "reverse_company" in models.content_type.meta.fields
    assert "content_type" in ContentTypeTag.fields
    assert "content_type" not in ContentTypeTag.table.columns


async def test_default_contenttypes():
    model1 = await Company.query.create(name="edgy inc")
    model2 = await Organisation.query.create(name="edgy org")

    assert model1.content_type.id is not None
    assert model1.content_type.name == "Company"
    assert model2.content_type.id is not None
    assert model2.content_type.name == "Organisation"
    assert await model1.content_type.get_instance() == model1
    assert await model2.content_type.get_instance() == model2
    assert await models.content_type.query.count() == 2


async def test_named_contenttype_field():
    person = await Person.query.create(name="foo", c={})
    loaded = await Person.query.get(id=person.id)
    assert loaded.c.id is not None
    assert loaded.c.name == "Person"
    assert await loaded.c.get_instance() == person


async def test_collision():
    model1 = await Company.query.create(
        name="collision-company",
        content_type={"collision_key": "tenant-1"},
    )
    assert model1.content_type.collision_key == "tenant-1"
    with pytest.raises(IntegrityError):
        await Organisation.query.create(
            name="collision-org",
            content_type={"collision_key": "tenant-1"},
        )
