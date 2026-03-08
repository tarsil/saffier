import pytest
import sqlalchemy

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class Asset(saffier.Model):
    name = saffier.CharField(max_length=100)
    hidden = saffier.ExcludeField()
    description = saffier.ComputedField(
        getter="get_description",
        setter="set_description",
        fallback_getter=lambda field, instance, owner: instance.name,
    )
    file_ref = saffier.FileField(null=True)
    image_ref = saffier.ImageField(null=True)
    tags = saffier.PGArrayField(sqlalchemy.String(), null=True)

    class Meta:
        registry = models

    @classmethod
    def get_description(cls, field, instance, owner=None):
        return instance.name.upper()

    @classmethod
    def set_description(cls, field, instance, value, owner=None):
        instance.__dict__["description_override"] = value


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await models.create_all()
    yield
    await models.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connection():
    with database.force_rollback():
        async with database:
            yield


async def test_virtual_fields_do_not_create_columns():
    columns = Asset.table.columns.keys()
    assert "hidden" not in columns
    assert "description" not in columns
    assert "file_ref" in columns
    assert "image_ref" in columns
    assert "tags" in columns


@pytest.mark.skipif(database.url.dialect != "postgresql", reason="PGArrayField is PostgreSQL only")
async def test_pg_array_and_file_image_roundtrip():
    created = await Asset.query.create(
        name="asset",
        file_ref="files/readme.txt",
        image_ref="images/logo.png",
        tags=["a", "b"],
    )
    loaded = await Asset.query.get(pk=created.pk)
    assert loaded.file_ref == "files/readme.txt"
    assert loaded.image_ref == "images/logo.png"
    assert loaded.tags == ["a", "b"]


async def test_computed_field_getter_and_setter():
    asset = await Asset.query.create(name="asset-two")
    loaded = await Asset.query.get(pk=asset.pk)
    assert loaded.description == "ASSET-TWO"

    loaded.description = "custom"
    assert loaded.description_override == "custom"
