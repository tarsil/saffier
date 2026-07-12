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


class CustomAdminUser(saffier.Model):
    name = saffier.CharField(max_length=100)
    secret = saffier.CharField(max_length=100, null=True)

    class Meta:
        registry = models
        tablename = "custom_admin_users"

    @classmethod
    def get_admin_marshall_config(
        cls,
        *,
        phase: str,
        for_schema: bool,
    ) -> dict[str, object]:
        """Hide ``secret`` from admin create and update workflows.

        This model-level hook is intentionally exercised through ``AdminSite``
        rather than direct marshall construction. The admin must honor the same
        phase-specific field policy in schemas and writes.
        """
        config = super().get_admin_marshall_config(phase=phase, for_schema=for_schema)
        if phase in {"create", "update"}:
            config["exclude"] = ["secret"]
        return config


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


async def test_admin_site_uses_model_admin_marshall_hooks_for_writes():
    site = AdminSite(registry=models)

    schema = site.get_model_editor_schema("CustomAdminUser", phase="create")
    assert "secret" not in schema["properties"]

    with pytest.raises(AdminValidationError) as create_error:
        await site.create_object("CustomAdminUser", {"name": "hidden", "secret": "blocked"})
    assert create_error.value.errors["secret"] == "Field is not writable."

    created = await CustomAdminUser.query.create(name="visible", secret="stored")
    encoded_pk = site.create_object_pk(created)

    with pytest.raises(AdminValidationError) as update_error:
        await site.update_object("CustomAdminUser", encoded_pk, {"secret": "changed"})
    assert update_error.value.errors["secret"] == "Field is not writable."

    updated = await site.update_object("CustomAdminUser", encoded_pk, {"name": "renamed"})
    assert updated.name == "renamed"
    assert updated.secret == "stored"
