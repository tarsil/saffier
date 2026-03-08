import pytest

import saffier
from saffier.contrib.autoreflection import AutoReflectModel
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_ALTERNATIVE_URL, DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL, use_existing=False, test_prefix="schema_reflect_")
source = saffier.Registry(database=database, schema="foo")


class Foo(saffier.Model):
    a = saffier.CharField(max_length=40)
    b = saffier.CharField(max_length=40, server_default="")

    class Meta:
        registry = source


class Bar(saffier.Model):
    a = saffier.CharField(max_length=40)

    class Meta:
        registry = source


class NotFoo(saffier.Model):
    a = saffier.CharField(max_length=40)

    class Meta:
        registry = source


@pytest.fixture(autouse=True, scope="function")
async def create_test_database():
    async with database:
        await source.create_all()
        yield
        if not database.drop:
            await source.drop_all()


async def test_basic_reflection_across_schema():
    reflected = saffier.Registry(database=database)

    class AutoAll(AutoReflectModel):
        class Meta:
            registry = reflected
            schemes = (None, "foo")

    class AutoFoo(AutoReflectModel):
        class Meta:
            registry = reflected
            include_pattern = r"^foos$"
            schemes = (None, "foo")

    class AutoBar(AutoReflectModel):
        class Meta:
            registry = reflected
            include_pattern = r"^bars"
            template = r"{tablename}_{tablename}"
            schemes = (None, "foo")

    async with reflected:
        assert (
            sum(
                1 for model in reflected.reflected.values() if model.__name__.startswith("AutoAll")
            )
            == 3
        )
        assert "bars_bars" in reflected.reflected
        assert (
            sum(
                1 for model in reflected.reflected.values() if model.__name__.startswith("AutoFoo")
            )
            == 1
        )


async def test_extra_reflection_across_schema():
    reflected = saffier.Registry(DATABASE_ALTERNATIVE_URL, extra={"another": database})

    class AutoFoo(AutoReflectModel):
        a = saffier.CharField(max_length=40)

        class Meta:
            registry = reflected
            include_pattern = r"^foos$"
            databases = ("another",)
            schemes = ("foo", None)

    async with reflected:
        assert (
            sum(
                1 for model in reflected.reflected.values() if model.__name__.startswith("AutoFoo")
            )
            == 1
        )
        obj = await reflected.get_model("AutoFoofoos").query.create(a="edgy")
        assert (await Foo.query.get(a="edgy")).id == obj.id
