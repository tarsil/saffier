from __future__ import annotations

import enum
import types

import pytest

import saffier
from saffier.exceptions import ValidationError
from saffier.testclient import DatabaseTestClient as Database
from saffier.testing.exceptions import ExcludeValue, InvalidModelError
from saffier.testing.factory import FactoryField, ModelFactory
from saffier.testing.factory.base import ModelFactoryContextImplementation
from saffier.testing.factory.faker import _FallbackFaker
from saffier.testing.factory.mappings import DEFAULT_MAPPING
from saffier.testing.factory.metaclasses import MetaInfo
from tests.settings import DATABASE_URL

database = Database(DATABASE_URL, full_isolation=False)
models = saffier.Registry(database=database)


class DeepCustomField(saffier.CharField):
    pass


class DeepFactoryModel(saffier.Model):
    name = saffier.CharField(max_length=100, null=True)
    quantity = saffier.IntegerField(null=True)
    note = saffier.CharField(max_length=100, null=True)

    class Meta:
        registry = models


class DeepNoMappingModel(saffier.Model):
    code = DeepCustomField(max_length=32, null=True)

    class Meta:
        registry = models


class _BoolFaker(_FallbackFaker):
    def __init__(self, *, pybool_result: bool):
        super().__init__()
        self.pybool_result = pybool_result

    def pybool(self, probability: int | None = None) -> bool:
        return self.pybool_result


def test_factory_context_proxies_faker_attributes():
    context = ModelFactoryContextImplementation(faker=types.SimpleNamespace(ping=lambda: "pong"))
    assert context.ping() == "pong"


def test_meta_info_copies_declared_slots():
    source_meta = types.SimpleNamespace(
        model=DeepFactoryModel, faker="faker", mappings={"A": None}
    )
    info = MetaInfo(meta=source_meta, callcounts={1: 3})
    assert info.model is DeepFactoryModel
    assert info.faker == "faker"
    assert info.mappings == {"A": None}
    assert info.callcounts == {1: 3}


def test_factory_build_values_callback_and_random_branches():
    class DeepFactory(ModelFactory, model_validation="none"):
        class Meta:
            model = DeepFactoryModel

        name = FactoryField(parameters={"randomly_unset": True})
        quantity = FactoryField(parameters={"randomly_nullify": True})

    string_values = DeepFactory().build_values(
        faker=_FallbackFaker(),
        parameters={"note": "word"},
        exclude={"name", "quantity"},
    )
    assert isinstance(string_values["note"], str)

    callable_values = DeepFactory().build_values(
        faker=_BoolFaker(pybool_result=True),
        parameters={
            "name": lambda field, context, params: "ignored",
            "quantity": lambda field, context, params: 42,
        },
        exclude={"note"},
    )
    assert "name" not in callable_values
    assert callable_values["quantity"] is None

    callable_without_random_flags = DeepFactory().build_values(
        faker=_BoolFaker(pybool_result=False),
        parameters={"note": lambda field, context, params: "from-callback"},
        exclude={"name", "quantity"},
    )
    assert callable_without_random_flags["note"] == "from-callback"

    mapping_values = DeepFactory().build_values(
        faker=_BoolFaker(pybool_result=True),
        parameters={
            "name": {"randomly_unset": True},
            "quantity": {"randomly_nullify": True},
        },
        exclude={"note"},
    )
    assert "name" not in mapping_values
    assert mapping_values["quantity"] is None


def test_factory_build_database_and_schema_assignment_paths():
    class DeepFactory(ModelFactory, model_validation="none"):
        class Meta:
            model = DeepFactoryModel

    built_without_explicit_db = DeepFactory().build(database=False, schema=False)
    assert built_without_explicit_db._db_loaded is True

    sentinel_database = object()
    built_with_explicit_db = DeepFactory().build(database=sentinel_database, schema="tenant-x")
    assert built_with_explicit_db.database is sentinel_database
    assert built_with_explicit_db.__using_schema__ == "tenant-x"


def test_metaclass_validation_modes_and_invalid_model(monkeypatch: pytest.MonkeyPatch):
    from saffier.testing.factory import base as factory_base
    from saffier.testing.factory import metaclasses as factory_metaclasses

    warnings: list[str] = []
    monkeypatch.setattr(factory_metaclasses.terminal, "write_warning", warnings.append)

    def raise_validation_error(self, **kwargs):
        raise ValidationError(text="invalid")

    monkeypatch.setattr(factory_base.ModelFactory, "build", raise_validation_error)
    with pytest.raises(ValidationError):

        class PedanticFactory(ModelFactory, model_validation="pedantic"):
            class Meta:
                model = DeepFactoryModel

            pass

    def raise_runtime_error(self, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(factory_base.ModelFactory, "build", raise_runtime_error)

    class WarnFactory(ModelFactory, model_validation="warn"):
        class Meta:
            model = DeepFactoryModel

        pass

    assert WarnFactory.meta.model is DeepFactoryModel
    assert any("failed producing a valid sample model" in warning for warning in warnings)

    with pytest.raises(RuntimeError):

        class ErrorFactory(ModelFactory, model_validation="error"):
            class Meta:
                model = DeepFactoryModel

            pass

    with pytest.raises(InvalidModelError):

        class InvalidFactory(ModelFactory, model_validation="none"):
            class Meta:
                model = 123

            pass


def test_metaclass_mapping_and_inheritance_warnings(monkeypatch: pytest.MonkeyPatch):
    from saffier.testing.factory import metaclasses as factory_metaclasses

    warnings: list[str] = []
    monkeypatch.setattr(factory_metaclasses.terminal, "write_warning", warnings.append)

    class ExplicitMissingMappingFactory(ModelFactory, model_validation="none"):
        class Meta:
            model = DeepNoMappingModel

        exclude_autoincrement = False
        code = FactoryField()

    assert ExplicitMissingMappingFactory.meta.model is DeepNoMappingModel
    assert any("DeepCustomField" in warning for warning in warnings)

    warnings.clear()

    class AutoMissingMappingFactory(ModelFactory, model_validation="none"):
        class Meta:
            model = DeepNoMappingModel

        pass

    assert AutoMissingMappingFactory.meta.model is DeepNoMappingModel
    assert any("DeepCustomField" in warning for warning in warnings)

    warnings.clear()

    class ParentFactory(ModelFactory, model_validation="none"):
        class Meta:
            model = DeepFactoryModel

        transient = FactoryField(
            field_type="CharField", callback=lambda field, context, params: "x", no_copy=True
        )
        name = FactoryField()

    class ChildFactory(ParentFactory, model_validation="none"):
        class Meta:
            model = DeepFactoryModel

        pass

    assert "transient" not in ChildFactory.meta.fields
    assert "name" in ChildFactory.meta.fields

    ParentFactory.meta.mappings.pop("CharField", None)
    warnings.clear()

    class WarningChildFactory(ParentFactory, model_validation="none"):
        class Meta:
            model = DeepFactoryModel

        pass

    assert WarningChildFactory.meta.model is DeepFactoryModel
    assert any('Mapping for field type "CharField" not found.' in warning for warning in warnings)


def test_default_mapping_helpers_for_choices_and_arrays():
    faker = types.SimpleNamespace(
        random_element=lambda elements: elements[0],
        word=lambda: "token",
    )

    tuple_choice_field = types.SimpleNamespace(
        owner=types.SimpleNamespace(
            meta=types.SimpleNamespace(
                model=types.SimpleNamespace(
                    fields={"choice": types.SimpleNamespace(choices=[("a", "A"), "b"])}
                )
            )
        ),
        name="choice",
    )
    assert DEFAULT_MAPPING["ChoiceField"](tuple_choice_field, {"faker": faker}, {}) == "a"

    class Language(enum.Enum):
        EN = "en"
        PT = "pt"

    enum_choice_field = types.SimpleNamespace(
        owner=types.SimpleNamespace(
            meta=types.SimpleNamespace(
                model=types.SimpleNamespace(
                    fields={"choice": types.SimpleNamespace(choices=Language)}
                )
            )
        ),
        name="choice",
    )
    enum_result = DEFAULT_MAPPING["CharChoiceField"](enum_choice_field, {"faker": faker}, {})
    assert isinstance(enum_result, Language)

    missing_choices_field = types.SimpleNamespace(
        owner=types.SimpleNamespace(
            meta=types.SimpleNamespace(
                model=types.SimpleNamespace(fields={"choice": types.SimpleNamespace(choices=None)})
            )
        ),
        name="choice",
    )
    with pytest.raises(ExcludeValue):
        DEFAULT_MAPPING["ChoiceField"](missing_choices_field, {"faker": faker}, {})

    assert DEFAULT_MAPPING["PGArrayField"](None, {"faker": faker}, {"count": 2}) == [
        "token",
        "token",
    ]
