import pytest

import saffier
from saffier.contrib.autoreflection import AutoReflectModel
from saffier.testclient import DatabaseTestClient
from tests.settings import DATABASE_URL

pytestmark = pytest.mark.anyio

database = DatabaseTestClient(DATABASE_URL)
source = saffier.Registry(database=database)


class Foo(saffier.Model):
    a = saffier.CharField(max_length=40)
    b = saffier.CharField(max_length=40, default="")

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


@pytest.fixture(autouse=True, scope="module")
async def create_test_database():
    await source.create_all()
    yield
    await source.drop_all()


@pytest.fixture(autouse=True)
async def rollback_connection():
    with database.force_rollback():
        async with database:
            yield


async def test_basic_reflection_patterns():
    reflected = saffier.Registry(database=database)

    class AutoAll(AutoReflectModel):
        class Meta:
            registry = reflected
            include_pattern = r"^(foos|bars|notfoos)$"

    class AutoNever(AutoReflectModel):
        non_matching = saffier.CharField(max_length=40)

        class Meta:
            registry = reflected
            template = "AutoNever"

    class AutoNever2(AutoReflectModel):
        class Meta:
            registry = reflected
            template = "AutoNever2"
            exclude_pattern = ".*"

    class AutoFoo(AutoReflectModel):
        class Meta:
            registry = reflected
            include_pattern = r"^foos$"

    class AutoBar(AutoReflectModel):
        class Meta:
            registry = reflected
            include_pattern = r"^bars$"
            template = r"{tablename}_{tablename}"

    await reflected.reflect_pattern_models()

    assert (
        sum(1 for model in reflected.reflected.values() if model.__name__.startswith("AutoAll"))
        == 3
    )
    assert "AutoFoofoos" in reflected.reflected
    assert "bars_bars" in reflected.reflected
    assert "AutoNever" not in reflected.reflected
    assert "AutoNever2" not in reflected.reflected
    assert AutoAll.meta.template is not None
    assert "AutoAll" in reflected.pattern_models


async def test_reflected_models_are_queryable():
    reflected = saffier.Registry(database=database)

    class AutoFoo(AutoReflectModel):
        class Meta:
            registry = reflected
            include_pattern = r"^foos$"

    await reflected.reflect_pattern_models()
    model = reflected.get_model("AutoFoofoos")
    created = await model.query.create(a="edgy", b="x")
    fetched = await Foo.query.get(a="edgy")
    assert created.id == fetched.id
