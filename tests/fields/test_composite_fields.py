import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = Database(DATABASE_URL)
models = saffier.Registry(database=database)


class Customer(saffier.Model):
    id = saffier.IntegerField(primary_key=True, autoincrement=True)
    first_name = saffier.CharField(max_length=120)
    last_name = saffier.CharField(max_length=120)

    # Groups existing columns under a single virtual attribute.
    full_name = saffier.CompositeField(inner_fields=["first_name", "last_name"])

    # Injects real columns with a dedicated prefix.
    contact = saffier.CompositeField(
        inner_fields=[
            ("email", saffier.EmailField(max_length=255, null=True)),
            ("phone", saffier.CharField(max_length=64, null=True)),
        ],
        prefix_embedded="contact_",
    )

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


async def test_composite_field_embeds_columns_and_keeps_virtual_parent():
    columns = Customer.table.columns.keys()

    assert "full_name" not in columns
    assert "contact" not in columns
    assert "contact_email" in columns
    assert "contact_phone" in columns
    assert "contact_email" in Customer.fields
    assert "contact_phone" in Customer.fields
    assert Customer.fields["full_name"].is_virtual
    assert Customer.fields["contact"].is_virtual


async def test_composite_get_and_set_updates_underlying_fields():
    customer = await Customer.query.create(
        first_name="John",
        last_name="Doe",
        contact_email="john@example.com",
        contact_phone="+41-111-222",
    )

    loaded = await Customer.query.get(pk=customer.pk)
    assert loaded.full_name == {"first_name": "John", "last_name": "Doe"}
    assert loaded.contact == {"email": "john@example.com", "phone": "+41-111-222"}

    loaded.full_name = {"first_name": "Jane", "last_name": "Roe"}
    loaded.contact = {"email": "jane@example.com"}
    await loaded.save()

    reloaded = await Customer.query.get(pk=customer.pk)
    assert reloaded.first_name == "Jane"
    assert reloaded.last_name == "Roe"
    assert reloaded.contact_email == "jane@example.com"
    assert reloaded.contact_phone == "+41-111-222"


async def test_composite_embedded_fields_are_copied_between_expansions() -> None:
    field = saffier.CompositeField(
        inner_fields=[("city", saffier.CharField(max_length=100))],
    )

    embedded_one = field.get_embedded_fields("address", {})
    embedded_two = field.get_embedded_fields("address", {})

    assert embedded_one["city"] is not embedded_two["city"]
