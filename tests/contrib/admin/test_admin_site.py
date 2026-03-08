import pytest

import saffier
from saffier.contrib.admin import AdminSite
from saffier.contrib.admin.exceptions import AdminModelNotFound, AdminValidationError
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class User(saffier.Model):
    name = saffier.CharField(max_length=100)
    active = saffier.BooleanField(default=False)

    class Meta:
        registry = models


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


async def test_admin_site_crud_flow():
    site = AdminSite(registry=models)

    created = await site.create_object("User", {"name": "foo"})
    assert created.name == "foo"
    assert created.active is False

    encoded_pk = site.create_object_pk(created)
    fetched = await site.get_object("User", encoded_pk)
    assert fetched.pk == created.pk

    updated = await site.update_object("User", encoded_pk, {"active": "true"})
    assert updated.active is True

    deleted = await site.delete_object("User", encoded_pk)
    assert deleted == 1
    assert await User.query.count() == 0


async def test_admin_site_validation_errors():
    site = AdminSite(registry=models)

    with pytest.raises(AdminValidationError) as exc:
        await site.create_object("User", {})

    assert "name" in exc.value.errors


async def test_admin_site_pagination_and_schema():
    site = AdminSite(registry=models)

    await User.query.bulk_create([{"name": f"user-{i}"} for i in range(5)])
    page = await site.list_objects("User", page=1, page_size=2)

    assert len(page.content) == 2
    assert page.is_first is True
    assert page.is_last is False

    schema = site.get_model_schema("User")
    field_names = [field["name"] for field in schema["fields"]]
    assert "name" in field_names
    assert schema["pk_name"] == "id"


async def test_admin_site_filters_and_payload_errors():
    site = AdminSite(registry=models, include_models={"User"})
    assert "User" in site.get_registered_models()
    with pytest.raises(AdminModelNotFound):
        site.get_model("Missing")

    created = await User.query.create(name="alice")
    encoded_pk = site.create_object_pk(created)

    with pytest.raises(AdminValidationError):
        site.parse_object_pk("not-base64")

    payload = site.form_to_payload(
        type(
            "Form",
            (),
            {
                "get": lambda self, k: None,
                "multi_items": lambda self: [("name", "john"), ("_csrf", "x")],
            },
        )()
    )
    assert payload == {"name": "john"}

    with pytest.raises(AdminValidationError):
        site.form_to_payload(
            type("Form", (), {"get": lambda self, k: "{", "multi_items": lambda self: []})()
        )

    search_page = await site.list_objects("User", page=1, page_size=10, search="ali")
    assert len(search_page.content) >= 1

    with pytest.raises(AdminValidationError):
        await site.update_object("User", encoded_pk, {"unknown": "value"})
