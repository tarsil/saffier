from __future__ import annotations

import asyncio
import types

import pytest

import saffier
from saffier.testclient import DatabaseTestClient as Database
from saffier.testing.exceptions import ExcludeValue
from saffier.testing.factory import FactoryField, ModelFactory
from saffier.testing.factory import context_vars as factory_context_vars
from saffier.testing.factory import faker as factory_faker
from saffier.testing.factory.base import ModelFactoryContextImplementation
from saffier.testing.factory.mappings import DEFAULT_MAPPING
from saffier.testing.factory.types import ModelFactoryContext
from saffier.testing.factory.utils import (
    default_wrapper,
    edgy_field_param_extractor,
    remove_unparametrized_relationship_fields,
)
from tests.settings import DATABASE_URL

database = Database(DATABASE_URL, full_isolation=False)
models = saffier.Registry(database=database)


class FactoryUser(saffier.Model):
    name = saffier.CharField(max_length=100, null=True)
    age = saffier.IntegerField(default=18)

    class Meta:
        registry = models


def test_factory_faker_fallback_methods(monkeypatch: pytest.MonkeyPatch):
    fallback = factory_faker._FallbackFaker()
    assert isinstance(fallback.pyint(min_value=1, max_value=2), int)
    assert isinstance(fallback.random_int(min=1, max=2), int)
    assert isinstance(fallback.pyfloat(), float)
    assert isinstance(fallback.pybool(), bool)
    assert isinstance(fallback.word(), str)
    assert isinstance(fallback.sentence(), str)
    assert fallback.email().endswith("@example.com")
    assert fallback.url().startswith("https://")
    assert isinstance(fallback.binary(length=4), bytes)
    assert isinstance(fallback.uuid4(), str)
    assert fallback.random_element(elements=[1, 2]) in {1, 2}

    monkeypatch.setitem(
        __import__("sys").modules, "faker", types.SimpleNamespace(Faker=lambda: "ok")
    )
    assert factory_faker.make_faker() == "ok"


def test_factory_field_helpers_and_callcount():
    context = ModelFactoryContextImplementation(
        faker=factory_faker._FallbackFaker(),
        exclude_autoincrement=True,
        depth=0,
        callcounts={},
    )
    token = factory_context_vars.model_factory_context.set(context)
    try:
        field = FactoryField(
            callback=lambda f, ctx, kwargs: kwargs["value"],
            parameters={"value": lambda f, ctx, name: "x"},
            field_type=saffier.IntegerField,
        )
        field.owner = types.SimpleNamespace(
            meta=types.SimpleNamespace(
                model=types.SimpleNamespace(
                    meta=types.SimpleNamespace(fields={"name": saffier.CharField(max_length=1)})
                ),
                mappings={"CharField": lambda f, c, p: "mapped"},
            )
        )
        field.name = "name"
        assert field.field_type == "IntegerField"
        params = field.get_parameters(context=context)
        assert params["value"] == "x"
        assert field(context=context, parameters=params) == "x"
        assert field.inc_callcount() == 1
        assert field.get_callcount() == 1
        del field.field_type
        assert field.field_type == ""
        copied = field.__copy__()
        assert copied.name == field.name
    finally:
        factory_context_vars.model_factory_context.reset(token)


def test_factory_utils_wrappers():
    class _Field:
        name = "age"
        owner = types.SimpleNamespace(
            meta=types.SimpleNamespace(
                model=types.SimpleNamespace(
                    meta=types.SimpleNamespace(
                        fields={"age": types.SimpleNamespace(ge=2, le=5, multiple_of=None)}
                    )
                )
            )
        )

    context: ModelFactoryContext = {
        "faker": factory_faker._FallbackFaker(),
        "exclude_autoincrement": True,
        "depth": 0,
        "callcounts": {},
    }
    field = _Field()

    wrapped = edgy_field_param_extractor(
        lambda f, ctx, kwargs: kwargs,
        defaults={"seed": "value"},
    )
    mapped = wrapped(field, context, {})
    assert mapped["min"] == 2
    assert mapped["max"] == 5
    assert mapped["seed"] == "value"

    wrapped_default = default_wrapper("pyint", {"min_value": 1, "max_value": 1})
    assert wrapped_default(field, context, {}) == 1


def test_remove_unparametrized_relationship_fields():
    model = types.SimpleNamespace(
        meta=types.SimpleNamespace(
            foreign_key_fields={"user": object()},
            many_to_many_fields={},
            fields={"user": types.SimpleNamespace(has_default=lambda: True)},
        )
    )
    kwargs = {"parameters": {}, "exclude": set()}
    remove_unparametrized_relationship_fields(model, kwargs)
    assert "user" in kwargs["exclude"]


def test_mapping_callbacks_and_factory_build_paths(monkeypatch: pytest.MonkeyPatch):
    class UserFactory(ModelFactory):
        class Meta:
            model = FactoryUser

        name = FactoryField(
            callback=lambda field, context, parameters: parameters["value"],
            parameters={"value": "abc"},
        )

    built = UserFactory().build()
    assert built.name == "abc"
    assert UserFactory().saffier_fields["name"] is FactoryUser.fields["name"]

    random_null = FactoryField(callback=lambda field, context, parameters: "x", parameters={})
    random_null.owner = UserFactory
    random_null.name = "name"
    token = factory_context_vars.model_factory_context.set(
        ModelFactoryContextImplementation(
            faker=types.SimpleNamespace(pybool=lambda probability=None: True),
            exclude_autoincrement=True,
            depth=0,
            callcounts={},
        )
    )
    try:
        with pytest.raises(ExcludeValue):
            raise ExcludeValue()
    finally:
        factory_context_vars.model_factory_context.reset(token)

    monkeypatch.setattr(
        "saffier.testing.factory.base.run_sync",
        lambda awaitable: (awaitable.close(), "saved")[1],
    )
    assert UserFactory().build(save=True) == "saved"

    class SaveFactory(ModelFactory):
        class Meta:
            model = FactoryUser

    class StubInstance:
        async def save(self):
            return "ok"

    monkeypatch.setattr(SaveFactory, "build", lambda self, **kwargs: StubInstance())
    saved = asyncio.run(SaveFactory().build_and_save())
    assert saved == "ok"

    assert DEFAULT_MAPPING["DurationField"](None, {"faker": factory_faker._FallbackFaker()}, {})
